"""Run the separately authorized overnight NAS acceptance with an absolute end.

Capacity precedes original Rust under both engines. Only two successful original
Rust jobs permit full releases. Every stage retains its own namespace. A NAS-local
watchdog restores the seven applications even if this Windows process disappears.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

import nas_release_vm as vm
from nas_followup_support import inner, jenkins_api, production_jobs, start_jenkins
from nas_gitea_target import idle
from nas_progress import run_ids
from nas_ssh import ROOT
from run_nas_capacity_window import SOURCES as CAPACITY_SOURCES
from run_nas_capacity_window import capacity_evidence, prepare_on_nas
from run_nas_full_release_window import (
    SERVICES,
    action,
    infrastructure,
    require_rust_evidence,
    verify_recovery,
)

WINDOW = 'resource-window-night-20261014'
BASE = ROOT / 'test-results/nas-parity/followup'
PLAN = BASE / 'night-window-plan-20261014'
ROUNDS = ['night-capacity3584-20261014', 'night-capacity3840-20261014',
          'night-capacity4096-20261014', 'night-rust-leroy-20261014',
          'night-rust-jenkins-20261014', 'night-release-20261014']
DEADLINE = datetime.fromisoformat('2026-10-15T06:00:00+02:00').timestamp()
SOURCES = (*CAPACITY_SOURCES, 'scripts/run_nas_night_window.py', 'scripts/archive_nas_night_disk.py',
           'scripts/compare_nas_full_release.py', 'scripts/diagnose_nas_release_group.py',
           'scripts/compare_frozen_release_cpu_eight.py', 'scripts/compare_frozen_postdeploy_group.py',
           'infra/vm/graphato-lifecycle.py')


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    temporary = path.with_suffix(path.suffix + '.partial')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def proposed_plan():
    return {'user_approved': False, 'window': WINDOW, 'maximum_window_seconds': 36000,
            'absolute_deadline_epoch': DEADLINE, 'restoration_deadline_berlin': '2026-10-15T06:00:00+02:00',
            'restore_margin_seconds': 900, 'services': list(SERVICES), 'comparison_rounds': ROUNDS,
            'source_commit': vm.COMMIT, 'application_sources_and_tests_unchanged': True,
            'capacity_goal_mib': 6144, 'capacity_hold_seconds': 60, 'guest_memory_mib': 8192,
            'memory_high_profiles_mib': [3584, 3840, 4096], 'page_reporting_order': 0,
            'early_memory_pressure': True, 'original_rust_required_both_engines': True,
            'native_jenkins_changed': False, 'production_cutover': False,
            'script_sha256': {name: vm.digest(ROOT / name) for name in SOURCES}}


def require_approval():
    assert (PLAN / 'approval.json').is_file(), 'A separate explicit overnight approval is required'
    value = read(PLAN / 'approval.json')
    assert value['user_approved'] is True and value['explicit_user_request'].strip()
    assert all(value[key] == expected for key, expected in proposed_plan().items() if key != 'user_approved'), \
        'Overnight scope or source changed; retain the approved version'
    return value


def register_runs(remote, case):
    identities = run_ids(case)
    if identities:
        state = action(remote, 'status')
        for identity in identities - set(state['runs']):
            action(remote, 'register', identity)


def stage(folder, remote, label, args, *, case=None, minimum_remaining=1800):
    """Observe one process; never rerun a dispatch after an uncertain outcome."""
    require_approval()
    state = action(remote, 'status')
    assert state['phase'] == 'paused' and state['deadline'] == DEADLINE
    assert state['deadline'] - time.time() >= minimum_remaining + state['restore_margin_seconds']
    idle()
    assert not (folder / (label + '-started.json')).exists(), 'Retain and observe the existing stage'
    process = None
    with (folder / (label + '-stdout.log')).open('xb') as out, (folder / (label + '-stderr.log')).open('xb') as err:
        try:
            process = subprocess.Popen([sys.executable, *args], cwd=ROOT, stdout=out, stderr=err)
            write(folder / (label + '-started.json'), {'pid': process.pid, 'at_epoch': time.time(),
                                                     'original_ci_restarted': False})
            while process.poll() is None:
                if case is not None:
                    register_runs(remote, case)
                state = action(remote, 'status')
                write(folder / 'latest-window-state.json', state)
                assert state['phase'] == 'paused', 'NAS recovery guard ended this test window'
                assert time.time() < state['deadline'] - state['restore_margin_seconds']
                time.sleep(10)
            if case is not None:
                register_runs(remote, case)
            write(folder / (label + '-result.json'), {'exit_code': process.returncode, 'at_epoch': time.time()})
            assert process.returncode == 0, 'Stage failed; retain its terminal or uncertain evidence'
        finally:
            if process is not None and process.poll() is None:
                # Stop load and restore services before terminating its observer.
                action(remote, 'restore')
                process.terminate()
                process.wait(timeout=20)


def stop_private_jenkins():
    idle()
    if inner('inspect', 'jenkins-parity', '--format', '{{.State.Running}}').strip() == 'true':
        inner('stop', '--time', '120', 'jenkins-parity', timeout=150)


def capacity(folder, remote):
    start_jenkins()
    idle()
    assert not json.loads(jenkins_api('/queue/api/json?tree=items[id]')['text'])['items']
    jobs = json.loads(jenkins_api('/api/json?tree=jobs[name,nextBuildNumber]')['text'])
    write(folder / 'private-jenkins-before.json', jobs)
    selected = None
    try:
        for high in (3584, 3840, 4096):
            name = 'night-capacity' + str(high) + '-20261014'
            profile = 'nas-8g-ssd-soft-ram-' + str(high)
            args = [str(ROOT / 'scripts/probe_nas_vm_capacity.py'), '--round', name,
                    '--resource-window', WINDOW, '--resource-profile', profile,
                    '--page-reporting-order', '0', '--early-memory-pressure', '--target-hold-seconds', '60']
            stage(folder, remote, name, args)
            result = capacity_evidence(BASE / name)
            write(folder / (name + '-qualification.json'), result)
            current = json.loads(jenkins_api('/api/json?tree=jobs[name,nextBuildNumber]')['text'])
            assert current == jobs and not json.loads(jenkins_api('/queue/api/json?tree=items[id]')['text'])['items']
            summary = result['memory_summary']
            assert summary['minimum_host_available_kib'] >= 128 * 1024
            assert summary['minimum_host_swap_free_kib'] >= 2304 * 1024
            assert summary['guest_oom_kill_counters'] == [0] and len(summary['physical_nas_oom_kill_counters']) == 1
            print(json.dumps({'capacity_profile': profile, 'peak_mib': result['peak_allocated_mib'],
                              'qualified': result['qualified_synthetic_capacity']}), flush=True)
            if result['qualified_synthetic_capacity']:
                selected = profile
                break
            assert result['reason'] == 'conservative_host_admission_declined', 'Investigate before another profile'
    finally:
        stop_private_jenkins()
    write(folder / 'capacity-decision.json', {'qualified_profile': selected, 'original_ci_dispatched': False})
    assert selected is not None, 'No profile qualified 6 GiB; do not dispatch original CI'
    return selected


def archive(folder, remote, name, engine):
    stage(folder, remote, 'archive-' + name + '-' + engine,
          [str(ROOT / 'scripts/archive_nas_night_disk.py'), '--round', name, '--engine', engine])


def run():
    require_approval()
    assert time.time() + 3600 < DEADLINE
    folder = BASE / WINDOW
    assert not folder.exists(), 'Never reopen the previous window or redispatch original jobs'
    folder.mkdir()
    remote = '/volume1/docker/leroy-nas-parity/' + WINDOW
    prepare_on_nas(folder, remote, overnight=True)
    outcome = 'not_completed'
    try:
        write(folder / 'paused.json', action(remote, 'pause'))
        profile = capacity(folder, remote)
        for engine in ('leroy', 'jenkins'):
            name = 'night-rust-' + engine + '-20261014'
            case = BASE / name
            stage(folder, remote, name, [str(ROOT / 'scripts/diagnose_nas_release_group.py'),
                  '--folder', case.relative_to(ROOT).as_posix(), '--engine', engine, '--group', 'server-test',
                  '--resource-profile', profile, '--postgres-init', '--memory-trace',
                  '--page-reporting-order', '0', '--early-memory-pressure'], case=case, minimum_remaining=4500)
            write(folder / (engine + '-rust-qualified.json'), require_rust_evidence(case, engine))
            archive(folder, remote, name, engine)
        for engine in ('leroy', 'jenkins'):
            case = BASE / 'night-release-20261014'
            stage(folder, remote, 'full-release-' + engine,
                  [str(ROOT / 'scripts/compare_nas_full_release.py'), '--folder', case.relative_to(ROOT).as_posix(),
                   '--engine', engine, '--first-engine', 'leroy', '--resource-profile', profile,
                   '--postgres-init', '--memory-trace', '--page-reporting-order', '0', '--early-memory-pressure'],
                  case=case, minimum_remaining=8100)
            idle()
            vm.stop()
            stop_private_jenkins()
            archive(folder, remote, case.name, engine)
        outcome = 'original_release_comparison_collected'
    except Exception as error:
        outcome = 'stopped:' + type(error).__name__
        write(folder / 'operation-error.json', {'type': type(error).__name__, 'original_ci_restarted': False})
        raise
    finally:
        # This does not depend on Windows staying connected: the NAS guard also
        # executes it at 05:45 Berlin, preserving fifteen minutes for recovery.
        state = action(remote, 'restore')
        write(folder / 'restored-window.json', state)
        recovery = verify_recovery(folder, remote)
        after = infrastructure()
        write(folder / 'infrastructure-after.json', after)
        before = read(folder / 'infrastructure-before.json')
        production = production_jobs()
        write(folder / 'production-after.json', production)
        result = {'at': datetime.now(timezone.utc).isoformat(), 'outcome': outcome,
                  'all_seven_original_services_restored_healthy': True,
                  'restored_before_deadline': state['finished_at'] < DEADLINE,
                  'healthy_before_deadline': recovery['at_epoch'] < DEADLINE,
                  'native_jenkins_quiet': not production['active_builds'] and production['jobs'] ==
                      read(folder / 'production-before.json')['jobs'],
                  'infrastructure_unchanged': all(before[k] == after[k] for k in
                      ('services', 'configuration_sha256', 'postgres_durability', 'comparison_driver_sha256')),
                  'controller_process_unchanged': before['states']['controller'] == after['states']['controller'],
                  'controller_no_new_oom': all(before['controller_memory']['memory.events'][k] ==
                      after['controller_memory']['memory.events'][k] for k in ('oom', 'oom_kill')),
                  'production_cutover': False, 'production_ready': False}
        write(folder / 'window-result.json', result)
        print(json.dumps(result), flush=True)
        assert all(result[k] for k in ('restored_before_deadline', 'healthy_before_deadline',
                   'native_jenkins_quiet', 'infrastructure_unchanged', 'controller_process_unchanged', 'controller_no_new_oom'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--run-approved', action='store_true')
    args = parser.parse_args()
    assert args.prepare != args.run_approved
    if args.prepare:
        PLAN.mkdir(exist_ok=True)
        path = PLAN / 'prepared-plan.json'
        assert not path.exists(), 'Retain the previous plan'
        write(path, proposed_plan())
        print(json.dumps({'plan': str(path.relative_to(ROOT)), 'nas_actions': False}))
    else:
        run()


if __name__ == '__main__':
    main()
