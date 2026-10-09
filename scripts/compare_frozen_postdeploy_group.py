"""Compare original postdeploy groups from one retained snapshot; never replace acceptance."""

import argparse
import base64
import hashlib
import json
import re
import subprocess
import time
import urllib.parse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import PurePosixPath

from collect_nas_jenkins_evidence import PROGRAM as JENKINS_EVIDENCE
from compare_nas_antares import client
from compare_nas_job import collect_artifacts
from nas_followup_support import inner, jenkins_api, production_jobs, start_jenkins
from nas_gitea_target import idle
from nas_graphato_release_state import VM_PROGRAM
from nas_measurement_guard import begin, finish, qualification_report
from nas_ssh import ROOT, run_script
from prepare_nas_vm import guest, wait_guest_ready
from watch_nas_graphato_jenkins import PROGRAM as JENKINS_STATE
from watch_nas_graphato_via_leroy import JENKINS_ID

COMPOSE = ['docker', 'compose', '-f', 'infra/nas/compose.target-vm.yaml']
ACTIVE = {'running', 'waiting', 'queued'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def snapshot(operation, name, allowed):
    assert operation in {'-c', '-a'} and name in allowed
    info = json.loads(subprocess.check_output(['docker', 'inspect', 'leroy-nas-target-vm']))[0]
    assert not info['State']['Running']
    assert next(m['Name'] for m in info['Mounts'] if m['Destination'] == '/vm') == 'leroy-nas-target_disk'
    subprocess.run([*COMPOSE, 'run', '--rm', '--no-deps', '--entrypoint', 'qemu-img', 'vm',
                    'snapshot', operation, name, '/vm/system.qcow2'], cwd=ROOT, check=True,
                   capture_output=True, timeout=240)


def target(commit):
    value = json.loads(guest('sudo python3 -B -', 'COMMIT=' + repr(commit) + '\n' + VM_PROGRAM, timeout=90))
    assert len(value['containers']) == 4
    assert all(c['running'] and c['health'] == 'healthy' for c in value['containers'])
    assert value['postdeploy_control_directory']['uid'] == 0
    assert value['postdeploy_control_directory']['mode'] == '0o700'
    info = json.loads(subprocess.check_output(['docker', 'inspect', 'leroy-nas-target-vm']))[0]
    value['outer_vm_resources'] = {'memory_bytes': info['HostConfig']['Memory'],
                                   'nano_cpus': info['HostConfig']['NanoCpus'],
                                   'environment': [item for item in info['Config']['Env']
                                                   if item.startswith(('VM_CPUS=', 'VM_MEMORY_MB='))]}
    value['guest_resources'] = json.loads(guest('python3 -B -',
        "import json,os,pathlib\nprint(json.dumps({'cpu_count':os.cpu_count(),"
        "'memory_total_kib':next(int(line.split()[1]) for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemTotal:'))}))",
        timeout=30))
    return value


def restore(folder, engine, commit, baseline):
    marker = folder / (engine + '-target-before.json')
    if marker.exists():
        raise RuntimeError('A prepared engine must be resumed, not implicitly restored again')
    idle()
    production_before = begin(folder, engine + '-restore')
    preserved = 'graphato-group-' + commit[:12] + '-' + folder.name + '-' + engine + '-before'
    guest('sudo python3 - stop', (ROOT / 'infra/vm/graphato-lifecycle.py').read_text(), timeout=240)
    guest('sudo systemctl poweroff --no-block', timeout=30)
    subprocess.run([*COMPOSE, 'stop'], cwd=ROOT, check=True, capture_output=True, timeout=300)
    snapshot('-c', preserved, {preserved, baseline})
    snapshot('-a', baseline, {preserved, baseline})
    write(folder / (engine + '-snapshot.json'), {'at': timestamp(), 'restored': baseline,
          'previous_state_preserved': preserved, 'clean_shutdown': True,
          'volume': 'leroy-nas-target_disk', 'production_modified': False})
    subprocess.run([*COMPOSE, 'up', '-d'], cwd=ROOT, check=True, capture_output=True, timeout=180)
    wait_guest_ready()
    guest('sudo python3 - start', (ROOT / 'infra/vm/graphato-lifecycle.py').read_text(), timeout=240)
    value = target(commit)
    expected_cpus = read(folder / 'prepared.json').get('target_cpus', 4)
    assert value['outer_vm_resources']['nano_cpus'] == expected_cpus * 10**9
    assert 'VM_CPUS=' + str(expected_cpus) in value['outer_vm_resources']['environment']
    assert value['guest_resources']['cpu_count'] == expected_cpus
    assert all(v['state'] == 'missing' for v in value['receipt']['suites'].values())
    value['captured_at'] = timestamp()
    write(marker, value)
    finish(folder, engine + '-restore', production_before)
    print(json.dumps({'engine': engine, 'baseline_restored': baseline, 'prior_receipts': False}), flush=True)


def original_jenkins_state(job, number):
    script = 'BUILDS=' + repr({job: number}) + '\n' + JENKINS_STATE
    response = run_script("python3 - <<'PY'\n" + script + '\nPY\n',
                          ROOT / '.local/nas-ssh.json', sudo=True, timeout=60)
    assert response.returncode == 0, response.stderr[-1000:]
    return json.loads(response.stdout)[job]


def collect_jenkins(folder, job, number, commit):
    script = 'JOB=' + repr(job) + '\nNUMBER=' + repr(number) + '\n' + JENKINS_EVIDENCE
    response = run_script("python3 - <<'PY'\n" + script + '\nPY\n',
                          ROOT / '.local/nas-ssh.json', sudo=True, timeout=90)
    assert response.returncode == 0, response.stderr[-1000:]
    value = json.loads(response.stdout)
    assert not value['build']['building'] and commit in value['build']['checkout_revisions']
    (folder / 'jenkins-console.log').write_text(value['console'], encoding='utf-8')
    archive = folder / ('jenkins-' + str(number) + '-artifacts')
    for item in value['artifacts']:
        content = item.pop('content', None)
        if content is None:
            continue
        name = PurePosixPath(item['name'])
        assert not name.is_absolute() and '..' not in name.parts
        destination = archive.joinpath(*name.parts)
        assert destination.resolve().is_relative_to(archive.resolve())
        data = base64.b64decode(content, validate=True)
        assert len(data) == item['size'] and hashlib.sha256(data).hexdigest() == item['sha256']
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    write(folder / 'jenkins-build.json', value['build'])
    write(folder / 'jenkins-artifact-index.json', value['artifacts'])


def execute_engine(folder, engine, commit, job, parameters, baseline):
    done = folder / (engine + '-target-after.json')
    marker = folder / (engine + '-start.json')
    if done.exists():
        finish(folder, engine, read(marker).get('production_guard_before'))
        return
    if not marker.exists():
        restore(folder, engine, commit, baseline)
        production_before = begin(folder, engine)
        if engine == 'leroy':
            assert inner('inspect', 'jenkins-parity', '--format', '{{.Id}}').strip() == JENKINS_ID
            assert inner('inspect', 'jenkins-parity', '--format', '{{.State.Running}}').strip() == 'false'
            with closing(client()) as api:
                definitions = api.get('/api/pipelines').json()
                assert not any(row['enabled'] for row in definitions)
                spec = next(row['spec'] for row in definitions if row['id'] == job)
                write(folder / 'leroy-definition.json', spec)
                response = api.post('/api/pipelines/' + job + '/runs',
                                    json={'commit': commit, 'parameters': parameters})
                response.raise_for_status()
                started = {'at': timestamp(), 'id': response.json()['id']}
        else:
            start_jenkins()
            state = json.loads(jenkins_api('/api/json?tree=jobs[name,nextBuildNumber,lastBuild[building]]')['text'])
            assert not any((row.get('lastBuild') or {}).get('building') for row in state['jobs'])
            assert not json.loads(jenkins_api('/queue/api/json?tree=items[id]')['text'])['items']
            number = next(row['nextBuildNumber'] for row in state['jobs'] if row['name'] == job)
            config = jenkins_api('/job/' + job + '/config.xml')['text']
            write(folder / 'jenkins-definition.json', {'sha256': hashlib.sha256(config.encode()).hexdigest(),
                  'source': 'existing owned comparison job, not rewritten'})
            response = jenkins_api('/job/' + job + '/buildWithParameters',
                                   urllib.parse.urlencode(parameters), 'application/x-www-form-urlencoded')
            started = {'at': timestamp(), 'number': number, 'queue_url': response['headers'].get('Location')}
        started['production_guard_before'] = production_before
        write(marker, started)
        print(json.dumps({'engine': engine, 'started': started}), flush=True)
    started = read(marker)
    deadline = time.monotonic() + 8 * 3600
    previous = None
    while time.monotonic() < deadline:
        if engine == 'leroy':
            with closing(client()) as api:
                response = api.get('/api/runs/' + started['id'])
                response.raise_for_status()
                run = response.json()
            assert run['commit'] == commit and run['pipeline_id'] == job and run['parameters'] == parameters
            state = {'id': run['id'], 'status': run['status'],
                     'steps': {step['id']: step['status'] for step in run['steps']}}
            finished = run['status'] not in ACTIVE
        else:
            state = original_jenkins_state(job, started['number'])
            finished = state.get('started') and not state.get('building')
        if state != previous:
            print(json.dumps({'engine': engine, 'state': state}), flush=True)
            previous = state
        write(folder / (engine + '-progress.json'), {'at': timestamp(), **state})
        if finished:
            break
        time.sleep(20)
    else:
        raise TimeoutError('Retain active run and resume observation; do not implicitly retry or cancel')
    if engine == 'leroy':
        write(folder / 'leroy-run.json', run)
        with closing(client()) as api:
            collect_artifacts(api, run, folder)
            for step in run['steps']:
                response = api.get('/api/runs/' + run['id'] + '/logs/' + step['id'])
                response.raise_for_status()
                (folder / ('leroy-' + step['id'] + '.log')).write_text(response.json()['text'], encoding='utf-8')
    else:
        collect_jenkins(folder, job, started['number'], commit)
        idle()
        inner('stop', '--time', '120', 'jenkins-parity', timeout=150)
    value = target(commit)
    assert value['manifest'] == read(folder / (engine + '-target-before.json'))['manifest']
    write(done, value)
    finish(folder, engine, started.get('production_guard_before'))
    print(json.dumps({'engine': engine, 'execution_complete': True}), flush=True)


def rust_summary(data):
    events = []
    for line in data.decode(errors='replace').splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            events.append(row)
    expected = sum(row['test_count'] for row in events if row.get('type') == 'suite' and row.get('event') == 'started')
    terminal = [row for row in events if row.get('type') == 'test' and row.get('event') in {'ok', 'failed', 'ignored'}]
    counts = Counter(row['event'] for row in terminal)
    assert expected > 0 and sum(counts.values()) == expected, 'A partial log cannot prove a full Rust suite'
    return {'expected': expected, 'ok': counts['ok'], 'failed': counts['failed'], 'ignored': counts['ignored'],
            'failed_tests': [row['name'] for row in terminal if row['event'] == 'failed'],
            'test_inventory_sha256': hashlib.sha256(json.dumps(sorted(row['name'] for row in terminal)).encode()).hexdigest()}


def analyze(folder, commit, suite, group):
    import tarfile

    values = {}
    for engine in ('leroy', 'jenkins'):
        root = folder / ('leroy-artifacts' if engine == 'leroy' else
                         'jenkins-' + str(read(folder / 'jenkins-start.json')['number']) + '-artifacts')
        path, = root.rglob('artifacts.tar.gz')
        files = {}
        with tarfile.open(path) as archive:
            for member in archive:
                assert member.isfile() and 0 <= member.size <= 64 * 1024**2
                assert not PurePosixPath(member.name).is_absolute() and '..' not in PurePosixPath(member.name).parts
                assert member.name not in files and len(files) < 1000
                files[member.name] = archive.extractfile(member).read()
        receipt = json.loads(files['result.json'])
        assert receipt['commit'] == commit and receipt['suite'] == suite and receipt['requestedGroup'] == group
        assert receipt['cleanupComplete'] and not receipt['cancelled'] and not receipt['reused']
        value = {'requested_passed': receipt['requestedPassed'], 'complete_suite_passed': receipt['passed'],
                 'checks': receipt['checks'], 'cleanup_complete': True,
                 'archive_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                 'identity': {key: receipt[key] for key in ('commit', 'runtimeImageId', 'sourceSha256', 'buildTimestamp')}}
        if suite == 'quality' and group == 'server-test':
            assert set(receipt['checks']) == {'server-test'}
            value['rust'] = rust_summary(files['server-test.log'])
            assert receipt['requestedPassed'] == (value['rust']['failed'] == 0)
            original = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / commit
            original /= 'scenarios/root-private-existing-host/graphato-postdeploy-quality/jenkins-8-artifacts'
            original_archive, = original.rglob('artifacts.tar.gz')
            with tarfile.open(original_archive) as archive:
                baseline_rust = rust_summary(archive.extractfile('server-test.log').read())
            assert value['rust']['expected'] == baseline_rust['expected']
            assert value['rust']['test_inventory_sha256'] == baseline_rust['test_inventory_sha256']
            value['same_full_rust_test_inventory_as_original'] = True
        values[engine] = value
    assert values['jenkins']['identity'] == values['leroy']['identity']
    report = {'at': timestamp(), 'commit': commit, 'suite': suite, 'group': group, 'engines': values,
              **qualification_report(folder, ('leroy', 'jenkins')),
              'engine_order': read(folder / 'prepared.json').get('engine_order', ['leroy', 'jenkins']),
              'same_active_release': True, 'same_baseline_snapshot': True,
              'application_source_changed': False, 'application_settings_changed': False,
              'original_acceptance_result_replaced': False, 'production_replacement_ready': False,
              'scope': 'Supporting original-group comparison; complete release acceptance remains separate'}
    write(folder / 'analysis.json', report)
    print(json.dumps({'group_comparison_complete': True, 'results':
                     {engine: value.get('rust', value['checks']) for engine, value in values.items()}}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--suite', choices=['quality', 'web'], required=True)
    parser.add_argument('--group', choices=['server-test', 'soak'], required=True)
    parser.add_argument('--round', type=int, choices=[1, 2], required=True)
    parser.add_argument('--target-cpus', type=int, choices=[4, 8], default=4)
    parser.add_argument('--engine-order', choices=['leroy-first', 'jenkins-first'], default='leroy-first')
    parser.add_argument('--reason', help='Purpose of a distinct controlled comparison')
    args = parser.parse_args()
    if args.target_cpus == 8:
        override = ROOT / '.local/nas-parity/vm/target-cpu-eight.json'
        config = {'services': {'vm': {'cpus': 8, 'environment': {'VM_CPUS': '8'}}}}
        if override.exists():
            assert read(override) == config
        else:
            write(override, config)
        COMPOSE.extend(['-f', str(override)])
    assert re.fullmatch('[a-f0-9]{40}', args.commit)
    assert (args.suite, args.group) in {('quality', 'server-test'), ('web', 'soak')}
    base = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / args.commit
    frozen = read(base / 'frozen-master.json')
    assert frozen['commit'] == args.commit and not frozen['application_patches_applied']
    scenario = read(base / 'scenarios/root-private-existing-host/scenario.json')
    suffix = '' if args.target_cpus == 4 else '-cpu-eight'
    folder = base / 'controlled-groups' / (args.suite + '-' + args.group + suffix + '-round-' + str(args.round))
    folder.mkdir(parents=True, exist_ok=True)
    parameters = {'RELEASE_COMMIT': args.commit, 'CHECK_GROUP': args.group}
    order = ['leroy', 'jenkins'] if args.engine_order == 'leroy-first' else ['jenkins', 'leroy']
    if not (folder / 'prepared.json').exists():
        write(folder / 'prepared.json', {'at': timestamp(), 'parameters': parameters,
              'baseline_snapshot': scenario['baseline_snapshot'], 'production_before': production_jobs(),
              'source_commit_frozen': args.commit, 'all_triggers_disabled': True,
              'target_cpus': args.target_cpus, 'memory_and_test_container_limits_changed': False,
              'engine_order': order, 'comparison_reason': args.reason,
              'application_patches_applied': False, 'production_modified': False})
    else:
        assert read(folder / 'prepared.json')['parameters'] == parameters
        assert read(folder / 'prepared.json').get('engine_order', ['leroy', 'jenkins']) == order
    job = 'graphato-postdeploy-' + args.suite
    for engine in order:
        execute_engine(folder, engine, args.commit, job, parameters, scenario['baseline_snapshot'])
    write(folder / 'production-after.json', production_jobs())
    analyze(folder, args.commit, args.suite, args.group)


if __name__ == '__main__':
    main()
