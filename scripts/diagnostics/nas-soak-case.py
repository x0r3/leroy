"""Run the original Soak command with prebuilt images in the owned NAS daemon."""

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import tarfile
import threading
import time
import uuid

ROOT = pathlib.Path('/var/lib/leroy-soak/0ad540dd5780')
COMMIT = '0ad540dd578033d45e4d0c25d89fbe57b32102a4'
SOURCE_SHA = 'f0c737a8133cd73f6b34c66be5081316a7047a1881583532874b40abaec59708'
CASE_IDS = {'jenkins-1', 'leroy-1', 'leroy-2', 'jenkins-2'}


def docker(*args, timeout=30):
    return subprocess.check_output(['docker', *args], text=True, timeout=timeout).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, choices=sorted(CASE_IDS))
    args = parser.parse_args()
    inputs = json.loads((ROOT / 'inputs.json').read_text())
    assert inputs['commit'] == COMMIT and inputs['source_sha256'] == SOURCE_SHA
    assert not docker('ps', '-q', '--filter', 'label=io.graphato.e2e.owner')
    case = ROOT / 'cases' / args.case
    assert not case.exists(), 'Every original sample is retained; no implicit rerun'
    case.mkdir(parents=True, mode=0o700)
    work = case / 'work'
    work.mkdir(mode=0o700)
    source = work / 'source'
    source.mkdir(mode=0o755)
    helper = ROOT / 'source/deployments/linux/host/postdeploy.py'
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == inputs['helper_sha256']
    assert hashlib.sha256((ROOT / 'nas-passive-http.py').read_bytes()).hexdigest() == inputs['observer_sha256']
    spec = importlib.util.spec_from_file_location('original_nas_soak_host', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with (ROOT / 'verification-source.tar.gz').open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == SOURCE_SHA
    module.source_extract(ROOT / 'verification-source.tar.gz', source)
    for child in ('home', 'tmp', 'docker-config', 'artifacts', 'e2e-state'):
        (work / child).mkdir(mode=0o700)
    for path in (work, *work.iterdir()):
        if path.name != 'source':
            os.chown(path, 1000, 1000)
    module.STATE = case / 'private-state'
    module.STATE.mkdir(mode=0o700)
    executor = module.Executor(source, case / 'browser-soak.log')
    project = 'graphato-ci-check-' + uuid.uuid4().hex[:12]
    environment = {
        'GRAPHATO_WEB_TEST_IMAGE': inputs['worker_image_id'],
        'GRAPHATO_E2E_SERVER_IMAGE': inputs['runtime_image_id'],
        'GRAPHATO_E2E_HOST_POSTDEPLOY': '1', 'GRAPHATO_E2E_CI_PARENT': project,
        'GRAPHATO_TEST_SOURCE_COMMIT': COMMIT, 'GRAPHATO_TEST_SOURCE_SHA256': SOURCE_SHA,
        'GRAPHATO_WEB_E2E_SUITE': 'open', 'GRAPHATO_WEB_E2E_CASES': 'soak',
        'XDG_STATE_HOME': str(work / 'e2e-state'),
        'GRAPHATO_WEB_E2E_ARTIFACTS': str(work / 'artifacts'),
    }
    observer = case / 'observer'
    observer.mkdir(mode=0o700)
    observation = {'started': False, 'errors': []}
    done = threading.Event()

    def watch():
        try:
            while not done.wait(0.4):
                ids = docker('ps', '-q', '--filter', 'label=io.graphato.ci.development-smoke=' + project,
                             '--filter', 'label=com.docker.compose.service=server', timeout=8).split()
                if not ids:
                    continue
                assert len(ids) == 1
                server = json.loads(docker('inspect', ids[0], timeout=8))[0]
                assert server['Image'] == inputs['runtime_image_id']
                name = 'leroy-passive-soak-' + args.case
                command = [
                    'run', '-d', '--name', name, '--label', 'io.leroy.nas-soak=observer',
                    '--label', 'io.leroy.nas-soak.case=' + args.case,
                    '--network', 'none', '--pid', 'host', '--read-only', '--user', '0:0',
                    '--cap-drop', 'ALL', '--cap-add', 'NET_RAW', '--cap-add', 'SYS_ADMIN',
                    '--cap-add', 'SYS_PTRACE', '--cap-add', 'DAC_OVERRIDE',
                    '--security-opt', 'apparmor=graphato-server', '--security-opt', 'no-new-privileges:true',
                    '--memory', '64m', '--memory-swap', '64m', '--cpus', '0.1', '--pids-limit', '32',
                    '--mount', 'type=bind,src=' + str(ROOT / 'nas-passive-http.py') + ',dst=/observe.py,readonly',
                    '--mount', 'type=bind,src=' + str(observer) + ',dst=/metadata',
                    '--entrypoint', 'python3', inputs['runtime_image_id'], '-B', '/observe.py',
                    '--output', '/metadata/http-metadata.jsonl', '--network-namespace-pid', str(server['State']['Pid']),
                ]
                identity = docker(*command, timeout=20)
                assert re.fullmatch('[a-f0-9]{64}', identity)
                observation.update(started=True, container_id=identity, server_id=server['Id'])
                return
        except (OSError, ValueError, AssertionError, subprocess.SubprocessError) as error:
            observation['errors'].append(type(error).__name__)

    thread = threading.Thread(target=watch, daemon=True)
    started = time.time()
    thread.start()
    execution_error = None
    with module.cancellation() as interrupted:
        try:
            executor.run(*module.runner_command(inputs['runtime_image_id'], work, project, environment),
                         'scripts/e2e-web.mjs', timeout=3600)
        except (OSError, ValueError, AssertionError, subprocess.SubprocessError) as error:
            execution_error = type(error).__name__
        finally:
            interrupted['cleaning'] = True
            done.set()
            thread.join(timeout=35)
            assert not thread.is_alive(), 'Retain an incomplete observer startup'
            if observation.get('container_id'):
                identity = observation['container_id']
                info = json.loads(docker('inspect', identity))[0]
                assert info['Config']['Labels'].get('io.leroy.nas-soak.case') == args.case
                docker('stop', '--time', '5', identity, timeout=15)
                observation['exit_code'] = json.loads(docker('inspect', identity))[0]['State']['ExitCode']
                docker('rm', identity)
    artifacts = work / 'artifacts'
    result_path = artifacts / 'open/results.json'
    lifecycle_path = artifacts / 'lifecycle.json'
    case_results = json.loads(result_path.read_text()) if result_path.is_file() else []
    lifecycle = json.loads(lifecycle_path.read_text()) if lifecycle_path.is_file() else None
    original_case_executed = len(case_results) == 1 and case_results[0].get('id') == 'soak'
    remaining = docker('ps', '-q', '--filter', 'label=io.graphato.e2e.owner').split()
    cleanup = lifecycle is not None and lifecycle.get('ownedResourcesRemoved') is True and lifecycle.get('credentialsRemoved') is True and not remaining
    outcome = case_results[0] if original_case_executed else None
    provenance = json.loads((artifacts / 'provenance.json').read_text()) if (artifacts / 'provenance.json').is_file() else None
    if provenance:
        assert provenance['workerImageId'] == inputs['worker_image_id']
        assert provenance['runtimeImageId'] == inputs['runtime_image_id']
        assert provenance['runnerSource'] == {'commit': COMMIT, 'sourceArchiveSha256': SOURCE_SHA, 'dirty': False}
    metadata = observer / 'http-metadata.jsonl'
    if metadata.is_file():
        count, last = 0, None
        with metadata.open() as stream:
            for line in stream:
                count += 1
                last = json.loads(line)
        observation['rows'] = count
        with metadata.open('rb') as stream:
            observation['metadata_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
        observation['ended_cleanly'] = bool(last) and last['kind'] == 'observer-end'
        observation['parser_counts'] = last.get('counts') if observation['ended_cleanly'] else None
    result = {'case': args.case, 'commit': COMMIT, 'started_at_epoch': started, 'finished_at_epoch': time.time(),
              'inputs': inputs, 'original_case_executed': original_case_executed, 'case_result': outcome,
              'execution_error_type': execution_error, 'cleanup_complete': cleanup, 'lifecycle': lifecycle,
              'remaining_fixture_containers': remaining, 'observation': observation,
              'tests_and_application_modified': False, 'rate_limits_modified': False,
              'prebuilt_images_used': True, 'is_complete_pipeline_acceptance': False,
              'observer_overhead_excluded': False,
              'scope': 'Original Soak runner command and original host fixture limits on NAS; fresh fixtures and immutable prebuilt artifacts. CI dispatch diagnostic, not a full release gate.'}
    archive = case / 'artifacts.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        selected = module.artifact_files(artifacts) if artifacts.exists() else []
        selected += [case / 'browser-soak.log'] if (case / 'browser-soak.log').is_file() else []
        if metadata.is_file():
            selected.append(metadata)
        for path in selected:
            assert path.is_file() and not path.is_symlink() and path.stat().st_size < 64 * 1024**2
            if path.is_relative_to(artifacts):
                name = 'browser-soak/' + path.relative_to(artifacts).as_posix()
            elif path == metadata:
                name = 'http-metadata.jsonl'
            else:
                name = path.name
            tar.add(path, arcname=name, recursive=False)
    with archive.open('rb') as stream:
        result['artifact_archive_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    (case / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'case': args.case, 'original_case_executed': original_case_executed,
                      'passed': bool(outcome and outcome['passed']), 'cleanup_complete': cleanup,
                      'observer_started': observation['started']}), flush=True)
    assert original_case_executed and cleanup, 'Retain the precondition/cleanup failure; stop the comparison sequence'
    return 0 if outcome['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
