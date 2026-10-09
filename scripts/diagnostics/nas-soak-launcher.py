"""Identical CI dispatch for an unchanged original Soak sample in the NAS test daemon."""

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import time

ROOT = '/var/lib/leroy-soak/0ad540dd5780'
CASES = {'jenkins-1', 'leroy-1', 'leroy-2', 'jenkins-2'}


def docker(*args, timeout=30):
    return subprocess.check_output(['docker', *args], text=True, timeout=timeout).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, choices=sorted(CASES))
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--coordinator-sha256', required=True)
    args = parser.parse_args()
    assert re.fullmatch('sha256:[a-f0-9]{64}', args.runtime)
    assert re.fullmatch('[a-f0-9]{64}', args.coordinator_sha256)
    name = 'leroy-original-soak-' + args.case
    existing = subprocess.run(['docker', 'inspect', name], capture_output=True, timeout=30)
    assert existing.returncode != 0, 'Retain any earlier coordinator; no implicit rerun'
    output = pathlib.Path('diagnostic')
    output.mkdir(mode=0o700, exist_ok=False)
    probe = 'import hashlib,pathlib;print(hashlib.sha256(pathlib.Path(' + repr(ROOT + '/nas-soak-case.py') + ').read_bytes()).hexdigest())'
    observed = docker('run', '--rm', '--network', 'none', '--read-only', '--memory', '128m', '--user', '0:0',
                      '--mount', 'type=bind,src=' + ROOT + ',dst=' + ROOT + ',readonly',
                      '--entrypoint', 'python3', args.runtime, '-B', '-c', probe)
    assert observed == args.coordinator_sha256
    identity = docker('create', '--name', name, '--label', 'io.leroy.nas-soak=coordinator',
                      '--label', 'io.leroy.nas-soak.case=' + args.case,
                      '--network', 'host', '--read-only', '--user', '0:0', '--cap-drop', 'ALL',
                      '--cap-add', 'CHOWN', '--cap-add', 'DAC_OVERRIDE', '--security-opt', 'no-new-privileges:true',
                      '--memory', '256m', '--memory-swap', '256m', '--cpus', '0.5', '--pids-limit', '64',
                      '--mount', 'type=bind,src=' + ROOT + ',dst=' + ROOT,
                      '--mount', 'type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock',
                      '--env', 'DOCKER_HOST=unix:///var/run/docker.sock',
                      '--entrypoint', 'python3', args.runtime, '-B', ROOT + '/nas-soak-case.py', '--case', args.case)
    assert re.fullmatch('[a-f0-9]{64}', identity)
    before = json.loads(docker('inspect', identity))[0]
    assert before['Image'] == args.runtime
    started = time.time()
    with (output / 'coordinator-console.log').open('xb') as log:
        process = subprocess.run(['docker', 'start', '-a', identity], stdout=log, stderr=subprocess.STDOUT, timeout=3900)
    state = json.loads(docker('inspect', identity))[0]
    assert state['Config']['Labels']['io.leroy.nas-soak.case'] == args.case
    assert not state['State']['Running']
    receipt = {'case': args.case, 'container_id': identity, 'runtime_image_id': state['Image'],
               'started_at_epoch': started, 'finished_at_epoch': time.time(),
               'docker_start_exit_code': process.returncode, 'container_exit_code': state['State']['ExitCode'],
               'oom_killed': state['State']['OOMKilled'],
               'coordinator_limits': {key: state['HostConfig'][key] for key in ('Memory', 'MemorySwap', 'NanoCpus', 'PidsLimit')},
               'copied': [], 'complete_original_pipeline': False}
    for filename in ('result.json', 'artifacts.tar.gz'):
        copied = subprocess.run(['docker', 'cp', identity + ':' + ROOT + '/cases/' + args.case + '/' + filename,
                                 str(output / filename)], capture_output=True, timeout=90)
        if copied.returncode == 0:
            receipt['copied'].append(filename)
    (output / 'launcher-result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    assert receipt['copied'] == ['result.json', 'artifacts.tar.gz'], 'Retain coordinator and missing result for diagnosis'
    result = json.loads((output / 'result.json').read_text())
    with (output / 'artifacts.tar.gz').open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == result['artifact_archive_sha256']
    assert result['case'] == args.case and result['inputs']['runtime_image_id'] == args.runtime
    docker('rm', identity)
    assert result['original_case_executed'] and result['cleanup_complete'], 'Keep the failed infrastructure evidence'
    assert state['State']['ExitCode'] in (0, 1) and not state['State']['OOMKilled']
    passed = result['case_result']['passed']
    assert state['State']['ExitCode'] == (0 if passed else 1)
    print(json.dumps({'case': args.case, 'passed': passed, 'original_test_executed': True,
                      'fixture_cleanup_complete': True, 'same_dispatch_program': True}), flush=True)
    return state['State']['ExitCode']


if __name__ == '__main__':
    raise SystemExit(main())
