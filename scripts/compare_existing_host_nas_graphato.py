"""Run unchanged post-deployment pipelines against identical prepared-host snapshots."""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

from nas_followup_support import inner, jenkins_api, production_jobs, start_jenkins, wait_production_jobs
from nas_gitea_target import idle
from nas_graphato_release_state import VM_PROGRAM
from nas_ssh import ROOT
from prepare_nas_vm import guest, wait_guest_ready
from stage_nas_production_graphato import COMMIT
from watch_nas_graphato_via_leroy import JENKINS_ID

SCENARIO = 'root-private-existing-host'
BASE = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / COMMIT
FOLDER = BASE / 'scenarios' / SCENARIO
SNAPSHOT = 'graphato-existing-host-' + COMMIT[:12]
JOBS = {'graphato-release-acceptance', 'graphato-postdeploy-web', 'graphato-postdeploy-quality'}
COMPOSE = ['docker', 'compose', '-f', 'infra/nas/compose.target-vm.yaml']


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def phase(name, *args, failure_allowed=False):
    print('Existing-host comparison:', name, *args, flush=True)
    result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts' / name), *args], cwd=ROOT)
    if result.returncode and not failure_allowed:
        raise RuntimeError('Inspect retained phase failure: ' + name)


def snapshot(operation, name):
    assert operation in {'-c', '-a'} and name in {SNAPSHOT, SNAPSHOT + '-jenkins-result', SNAPSHOT + '-leroy-cancelled-95'}
    info = json.loads(subprocess.check_output(['docker', 'inspect', 'leroy-nas-target-vm']))[0]
    assert next(m['Name'] for m in info['Mounts'] if m['Destination'] == '/vm') == 'leroy-nas-target_disk'
    assert not info['State']['Running']
    subprocess.run([*COMPOSE, 'run', '--rm', '--no-deps', '--entrypoint', 'qemu-img', 'vm',
                    'snapshot', operation, name, '/vm/system.qcow2'], cwd=ROOT, check=True)


def stop_vm():
    idle()
    guest('sudo python3 - stop', (ROOT / 'infra/vm/graphato-lifecycle.py').read_text(), timeout=240)
    guest('sudo systemctl poweroff --no-block', timeout=30)
    subprocess.run([*COMPOSE, 'stop'], cwd=ROOT, check=True, timeout=300)


def start_vm():
    subprocess.run([*COMPOSE, 'up', '-d'], cwd=ROOT, check=True)
    wait_guest_ready()
    guest('sudo python3 - start', (ROOT / 'infra/vm/graphato-lifecycle.py').read_text(), timeout=240)


def target(engine, *, require_empty=False):
    program = f'COMMIT={COMMIT!r}\n' + VM_PROGRAM
    if require_empty:
        program += "\nassert not list(control.iterdir()), 'No previous suite evidence or fixture state may be reused'\n"
    value = json.loads(guest('sudo python3 -B -', program, timeout=90))
    expected = read(FOLDER / 'scenario.json')['baseline_release']
    assert value['manifest'] == expected
    assert len(value['containers']) == 4 and all(c['running'] and c['health'] == 'healthy' for c in value['containers'])
    control = value['postdeploy_control_directory']
    assert control['uid'] == 0 and control['mode'] == '0o700' and not control['is_symlink']
    if require_empty:
        assert all(s['state'] == 'missing' for s in value['receipt']['suites'].values())
    value.update(captured_at=datetime.now(timezone.utc).isoformat(), application_patches_applied=False)
    write(FOLDER / (engine + '-target-' + ('before' if require_empty else 'after') + '.json'), value)
    return value


def prepare():
    assert (BASE / 'current-source-analysis.json').is_file(), 'Finish the fresh-target comparison first'
    assert not FOLDER.exists(), 'An existing scenario must be resumed explicitly'
    current = read(BASE / 'graphato-ci/leroy-final-state.json')
    assert current['manifest']['commit'] == COMMIT and not current['application_patches_applied']
    idle()
    assert inner('inspect', 'jenkins-parity', '--format', '{{.Id}}').strip() == JENKINS_ID
    assert inner('inspect', 'jenkins-parity', '--format', '{{.State.Running}}').strip() == 'false'
    program = r'''
import hashlib,json,pathlib,stat
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
release=pathlib.Path('/opt/graphato/current').resolve(strict=True)
assert release.parent==pathlib.Path('/opt/graphato/releases')
manifest=json.loads((release/'manifest.json').read_text());assert manifest==EXPECTED
control=pathlib.Path('/var/lib/graphato-host/postdeploy');info=control.lstat()
assert not control.is_symlink() and stat.S_ISDIR(info.st_mode) and info.st_uid==0
assert stat.S_IMODE(info.st_mode)==0o755 and not list(control.iterdir())
helper=release/'deployments/linux/host/postdeploy.py'
assert hashlib.sha256(helper.read_bytes()).hexdigest()==manifest['files']['deployments/linux/host/postdeploy.py']
control.chmod(0o700)
assert stat.S_IMODE(control.stat().st_mode)==0o700
print(json.dumps({'path':str(control),'previous_mode':'0o755','prepared_mode':'0o700','uid':0,'empty':True,'application_source_unchanged':True,'scope':'owned isolated application test VM only'}))
'''
    prepared = json.loads(guest('sudo python3 -B -', f'EXPECTED={current["manifest"]!r}\n' + program, timeout=30))
    FOLDER.mkdir(parents=True)
    write(FOLDER / 'scenario.json', {'at': datetime.now(timezone.utc).isoformat(), 'commit': COMMIT,
          'scenario': SCENARIO, 'directory_preparation': prepared, 'baseline_release': current['manifest'],
          'baseline_snapshot': SNAPSHOT, 'same_active_build_both': True, 'separate_fresh_target_builds': False,
          'same_original_source_both': True, 'controller_and_ci_workers_on_nas': True,
          'application_patches_applied': False, 'production_modified': False,
          'scope': 'Pre-existing root-private control directory; distinct from retained fresh-installation failure. Both engines verify the same frozen Leroy-built application.'})
    for name in [*sorted(JOBS), 'graphato-ci']:
        folder = FOLDER / name
        folder.mkdir()
        (folder / 'prepared.json').write_bytes((BASE / name / 'prepared.json').read_bytes())
    write(FOLDER / 'production-jobs-before.json', production_jobs())
    stop_vm()
    snapshot('-c', SNAPSHOT)
    write(FOLDER / 'baseline-snapshot.json', {'snapshot': SNAPSHOT, 'clean_shutdown': True,
          'volume': 'leroy-nas-target_disk', 'commit': COMMIT, 'suite_receipts_present': False})
    start_vm()
    target('jenkins', require_empty=True)


def jenkins():
    assert (FOLDER / 'baseline-snapshot.json').is_file() and not (FOLDER / 'jenkins-release-numbers.json').exists()
    idle()
    target('jenkins', require_empty=True)
    if read(BASE / 'staged.json')['source_kind'] == 'frozen_master_revision':
        from nas_master_build_slot import wait_for_nas_build_slot

        wait_for_nas_build_slot()
    else:
        wait_production_jobs()
    start_jenkins()
    state = read_api('/api/json?tree=jobs[name,nextBuildNumber,lastBuild[building]]')
    assert not any((j.get('lastBuild') or {}).get('building') for j in state['jobs'])
    assert not read_api('/queue/api/json?tree=items[id]')['items']
    numbers = {j['name']: j['nextBuildNumber'] for j in state['jobs'] if j['name'] in JOBS}
    assert set(numbers) == JOBS
    write(FOLDER / 'jenkins-release-numbers.json', numbers)
    phase('compare_nas_job.py', 'graphato-release-acceptance', 'start-jenkins', '--candidate', COMMIT)
    phase('watch_nas_graphato_jenkins.py', '--candidate', COMMIT, '--builds',
          (FOLDER / 'jenkins-release-numbers.json').relative_to(ROOT).as_posix(), failure_allowed=True)
    observed = read(FOLDER / 'jenkins-release-watch.json')
    assert set(observed['collected']) == JOBS and all(not r['building'] for r in observed['builds'].values())
    target('jenkins')
    idle()
    inner('stop', '--time', '120', 'jenkins-parity', timeout=150)


def read_api(path):
    return json.loads(jenkins_api(path)['text'])


def leroy(*, retry=False):
    assert (FOLDER / 'jenkins-target-after.json').is_file() and not (FOLDER / 'leroy-snapshot-restore.json').exists()
    idle()
    assert inner('inspect', 'jenkins-parity', '--format', '{{.State.Running}}').strip() == 'false'
    stop_vm()
    preserved = SNAPSHOT + ('-leroy-cancelled-95' if retry else '-jenkins-result')
    snapshot('-c', preserved)
    snapshot('-a', SNAPSHOT)
    write(FOLDER / 'leroy-snapshot-restore.json', {'restored': SNAPSHOT,
          'previous_state_preserved': preserved, 'volume': 'leroy-nas-target_disk', 'explicit_retry': retry})
    start_vm()
    target('leroy', require_empty=True)
    phase('compare_nas_job.py', 'graphato-release-acceptance', 'start-leroy', '--candidate', COMMIT)
    run_id = read(FOLDER / 'graphato-release-acceptance/pair.json')['leroy_run']
    from watch_nas_graphato_leroy import authenticated_tree

    previous = None
    deadline = time.monotonic() + 9 * 3600
    while time.monotonic() < deadline:
        rows = authenticated_tree(run_id, COMMIT, JOBS)
        if rows != previous:
            print(json.dumps(rows), flush=True)
            write(FOLDER / 'leroy-progress.json', rows)
            previous = rows
        if not any(row['status'] in {'running', 'waiting', 'queued'} for row in rows.values()):
            break
        time.sleep(20)
    else:
        raise TimeoutError('Original suites still active; no cancellation or implicit retry')
    assert set(rows) == JOBS
    for name, row in rows.items():
        path = FOLDER / name / 'pair.json'
        pair = read(path)
        pair.update(leroy_run=row['id'], leroy_status=row['status'])
        write(path, pair)
        phase('compare_nas_job.py', name, 'leroy', '--candidate', COMMIT)
    target('leroy')
    after = production_jobs()
    write(FOLDER / 'production-jobs-after.json', after)
    write(FOLDER / 'executions.json', {'at': datetime.now(timezone.utc).isoformat(), 'commit': COMMIT,
          'jenkins': read(FOLDER / 'jenkins-release-watch.json'), 'leroy': rows,
          'same_active_release': True, 'same_baseline_snapshot': True, 'no_preexisting_suite_receipts_both': True,
          'application_patches_applied': False, 'production_modified': False,
          'production_jobs_unchanged': read(FOLDER / 'production-jobs-before.json')['jobs'] == after['jobs'],
          'receipt_and_failure_analysis_pending': True})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['prepare', 'jenkins', 'leroy', 'retry-leroy', 'all'])
    args = parser.parse_args()
    os.environ['LEROY_NAS_COMPARISON_SCENARIO'] = SCENARIO
    if args.phase == 'retry-leroy':
        assert (FOLDER / 'explicit-leroy-retry.json').is_file()
        leroy(retry=True)
        return
    for name in (['prepare', 'jenkins', 'leroy'] if args.phase == 'all' else [args.phase]):
        globals()[name]()


if __name__ == '__main__':
    main()
