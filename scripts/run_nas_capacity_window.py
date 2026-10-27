"""Prepare, or execute after new explicit approval, one one-hour capacity window.

Only seven reviewed NAS applications may pause. A NAS-local recovery watchdog
starts before the first stop and restores with a fifteen-minute margin. The
private Jenkins is started idle; no original CI job is dispatched.
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
from nas_ssh import ROOT, upload_file
from run_nas_full_release_window import SERVICES, action, infrastructure, verify_recovery

WINDOW = 'resource-window-capacity-order0-20261014'
ROUND = 'capacity-window-order0-20261014'
BASE = ROOT / 'test-results/nas-parity/followup'
PLAN = BASE / 'capacity-window-plan-20261014'
SOURCES = ('scripts/run_nas_capacity_window.py', 'scripts/probe_nas_vm_capacity.py',
           'scripts/nas_resource_window_guard.py', 'scripts/nas_vm_page_reporting.py',
           'scripts/nas_vm_memory_pressure.py', 'scripts/nas_vm_memory_trace.py',
           'scripts/nas_vm_cache.py', 'scripts/nas_release_vm.py',
           'scripts/run_nas_full_release_window.py', 'infra/vm/launch.py',
           'src/leroy/worker.py', 'src/leroy/engine.py')


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def proposed_plan():
    return {'user_approved': False, 'window': WINDOW, 'comparison_round': ROUND,
            'maximum_window_seconds': 3600, 'restore_margin_seconds': 900,
            'window_count': 1, 'services': list(SERVICES), 'synthetic_only': True,
            'original_ci_dispatched': False, 'private_jenkins_idle': True,
            'guest_memory_mib': 8192, 'page_reporting_order': 0, 'memory_high_mib': 3584,
            'target_anonymous_mib': 6144, 'target_hold_seconds': 60,
            'source_commit': vm.COMMIT, 'full_release_acceptance': False, 'production_ready': False,
            'script_sha256': {name: vm.digest(ROOT / name) for name in SOURCES}}


def require_approval():
    path = PLAN / 'approval.json'
    assert path.is_file(), 'The two earlier windows are closed; this one-hour pause needs new explicit approval'
    approval = json.loads(path.read_text())
    expected = proposed_plan()
    assert approval['user_approved'] is True
    assert isinstance(approval.get('explicit_user_request'), str) and approval['explicit_user_request'].strip()
    assert all(approval[key] == value for key, value in expected.items() if key != 'user_approved'), 'Approved scope or source changed'
    return approval


def capacity_evidence(case):
    final = json.loads((case / 'final-state.json').read_text())
    summary = json.loads((case / 'leroy-memory-summary.json').read_text())
    phases = json.loads((case / 'phases.json').read_text())
    qualification = json.loads((case / 'production-measurement-qualification-synthetic-capacity.json').read_text())
    starts = [p['at'] for p in phases if p.get('kind') == 'allocated' and p['allocated_mib'] == 6144]
    holds = [p['at'] for p in phases if p.get('kind') == 'held' and p['allocated_mib'] == 6144]
    held_seconds = max(holds) - min(starts) if starts and holds else None
    passed = (final['reason'] == 'synthetic_target_held' and final['peak_allocated_mib'] == 6144 and
              not final['vm_running'] and held_seconds is not None and held_seconds >= 60 and
              phases[-1].get('sampled_pages_intact') is True and
              summary['minimum_host_available_kib'] >= 128 * 1024 and
              summary['minimum_host_swap_free_kib'] >= 2304 * 1024 and
              summary['aligned_guest_host_samples'] > 0 and summary['guest_oom_kill_counters'] == [0] and
              len(summary['physical_nas_oom_kill_counters']) == 1 and
              qualification['native_jenkins_quiet_window_verified'])
    return {'reason': final['reason'], 'qualified_synthetic_capacity': passed,
            'peak_allocated_mib': final['peak_allocated_mib'], 'target_held_seconds': held_seconds,
            'memory_summary': summary, 'original_graphato_ci_passed': False}


def prepare_on_nas(folder, remote, *, overnight=False, approved_day_plan=None):
    assert overnight in {False, True, 'original'}
    daytime = approved_day_plan is not None
    if daytime:
        from run_nas_day_window import validate_approval

        approval = approved_day_plan
        validate_approval(approval)
        assert folder.name == approval['window'] and not overnight
    elif overnight:
        if overnight == 'original':
            import run_nas_original_night_window as original

            original.configure_attempt(folder.name.rsplit('-', 1)[-1] if folder.name.rsplit('-', 1)[-1] in {'b', 'c', 'd', 'e', 'f'} else 'a')
            require_night_approval = original.require_approval
        else:
            from run_nas_night_window import require_approval as require_night_approval

        approval = require_night_approval()
        assert folder.name == approval['window']
    else:
        require_approval()
    idle()
    state = vm.state()
    assert state is None or not state['State']['Running']
    assert inner('inspect', 'jenkins-parity', '--format', '{{.State.Running}}').strip() == 'false'
    production = production_jobs()
    assert not production['active_builds'] and production['older_concurrent_build_history_verified']
    write(folder / 'production-before.json', production)
    before = infrastructure()
    write(folder / 'infrastructure-before.json', before)
    worker_proof = 'worker-transport-candidate-20261014' if daytime or (overnight == 'original' and original.ATTEMPT in {'c', 'd', 'e', 'f'}) else 'worker-lease-cadence-20261014'
    qualified = json.loads((BASE / worker_proof / 'deployment-proof.json').read_text())
    if worker_proof == 'worker-transport-candidate-20261014':
        from nas_test_environment import require_current_jenkins

        identity = require_current_jenkins()
        assert not identity['running'], 'Private Jenkins must be idle before the resource window'
        write(folder / 'verified-jenkins-identity.json', identity)
        assert qualified['exact_linux_qualified_image_deployed'] and qualified['linux_worker_tests'] == 28
        assert qualified['request_timeouts_or_retries_changed'] is False
        assert vm.digest(ROOT / 'src/leroy/worker.py') == qualified['worker_sha256']
        assert vm.digest(ROOT / 'src/leroy/lease_trace.py') == qualified['lease_trace_sha256']
        runner = json.loads((BASE / 'runner-cadence-completion-20261015/deployment-proof.json').read_text())
        assert runner['exact_linux_qualified_image_deployed'] and runner['linux_runner_tests'] == 23
        assert before['services']['runner']['image'] == runner['runner_image']
        if daytime or original.ATTEMPT in {'d', 'e', 'f'}:
            storage = json.loads((BASE / 'engine-storage-20261015-b/deployment-proof.json').read_text())
            assert storage['qualified_worker_image_config_and_layers_unchanged'] and storage['linux_worker_tests'] == 28
            program = 'EXPECTED=' + repr(storage['engine_root']) + '\n' + r'''
import json,subprocess
c=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-docker-1']))[0]
assert next(m['Source'] for m in c['Mounts'] if m['Destination']=='/var/lib/docker')==EXPECTED
print('verified')
'''
            assert vm.remote(program, sudo=True, timeout=30).strip() == 'verified'
    controller = json.loads((BASE / 'controller-reconcile-locks-20261014/postgres-validation.json').read_text())
    assert controller['all_passed'] and controller['postgres_tests'] == 34
    from nas_console_binding import qualified_controller_image

    expected_controller = qualified_controller_image(controller['candidate_image'], approval if daytime else None)
    assert before['services']['controller']['image'] == expected_controller
    assert vm.digest(ROOT / 'src/leroy/engine.py') == controller['engine_sha256']
    worker_image = qualified['worker_image']
    if daytime and approval.get('attempt') in {'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'}:
        from nas_graphato_transport import binding

        transport = binding()
        assert approval['graphato_transport_binding'] == transport
        worker_image = transport['worker_image']
    program = 'NAMES=' + repr(SERVICES) + '\nWORKER=' + repr(worker_image) + '\n' + r'''
import json,pathlib,shutil,subprocess,tomllib
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
assert tomllib.loads((root/'config/runner.toml').read_text())['profiles']['graphato']['image']==WORKER
assert shutil.disk_usage('/overlay').free>=50*1024**3
rows=json.loads(subprocess.check_output(['docker','inspect',*NAMES],text=True,timeout=20))
assert len(rows)==7 and all(c['Name']=='/'+n for n,c in zip(NAMES,rows))
assert all(c['State']['Running'] and c['State'].get('Health',{}).get('Status') in (None,'healthy') for c in rows)
print(json.dumps([{'name':c['Name'].lstrip('/'),'id':c['Id']} for c in rows]))
'''
    reviewed = json.loads(vm.remote(program, sudo=True, timeout=45))
    plan = {'user_approved': True, 'maximum_window_seconds': 3600, 'graceful_stop_seconds': 120,
            'comparison_round': ROUND, 'synthetic_only': True, 'original_ci_dispatched': False,
            'containers': reviewed, 'production_counters': {name: v['number'] for name, v in production['jobs'].items()}}
    if overnight or daytime:
        plan.update({key: approval[key] for key in ('maximum_window_seconds', 'comparison_rounds',
                    'absolute_deadline_epoch', 'explicit_user_request', 'source_commit')})
        plan.pop('comparison_round')
        plan.pop('synthetic_only')
        plan.pop('original_ci_dispatched')
    if daytime and approval.get('attempt') in {'v', 'w', 'x', 'y'}:
        plan['continuation_authorization'] = approval['continuation_authorization']
    write(folder / 'plan.json', plan)
    staging = remote + '-input'
    program = 'import pathlib\n'
    for location in (remote, staging):
        program += ('p=pathlib.Path(' + repr(location) + ')\nassert not p.exists()\n'
                    "assert p.parent.resolve()==p.parent and (p.parent/'.leroy-owned').is_file()\np.mkdir(mode=0o700)\n")
    vm.remote(program, timeout=30)
    for name, source in (('plan.json', folder / 'plan.json'), ('guard.py', ROOT / 'scripts/nas_resource_window_guard.py')):
        upload_file(source, staging + '/' + name, vm.CREDENTIALS, timeout=60)
    program = ('P=' + repr(remote) + '\nS=' + repr(staging) + '\n' + r'''
import hashlib,os,pathlib,shutil
p=pathlib.Path(P);s=pathlib.Path(S);os.chown(p,0,0);p.chmod(0o700)
for name in ('plan.json','guard.py'):
 shutil.copyfile(s/name,p/name);os.chown(p/name,0,0);(p/name).chmod(0o600)
print(hashlib.sha256((p/'guard.py').read_bytes()).hexdigest())
''')
    assert vm.remote(program, sudo=True, timeout=30).strip() == vm.digest(ROOT / 'scripts/nas_resource_window_guard.py')
    write(folder / 'prepared-window.json', action(remote, 'prepare'))
    unit = folder.name
    args = ['systemd-run', '--unit=' + unit, '--property=Restart=on-failure', '--property=RestartSec=10',
            '--property=StandardOutput=null', '--property=StandardError=null', '/usr/bin/python3', remote + '/guard.py', 'watch']
    program = ('import json,subprocess\nr=subprocess.run(' + repr(args) + ',capture_output=True,timeout=20)\n'
               "assert r.returncode==0,'Watchdog not started; no services paused'\n"
               'assert subprocess.check_output(' + repr(['systemctl', 'is-active', unit + '.service']) +
               ",text=True,timeout=10).strip()=='active'\nprint(json.dumps({'watchdog_active':True}))")
    write(folder / 'watchdog.json', json.loads(vm.remote(program, sudo=True, timeout=40)))


def run():
    require_approval()
    folder = BASE / WINDOW
    assert not folder.exists(), 'Retain the previous window; no implicit reopening'
    folder.mkdir()
    remote = '/volume1/docker/leroy-nas-parity/' + WINDOW
    vm.configure(ROUND, 'nas-8g-ssd-soft-ram-3584')
    prepare_on_nas(folder, remote)
    process = None
    qualification = None
    try:
        write(folder / 'paused.json', action(remote, 'pause'))
        start_jenkins()
        idle()
        assert not json.loads(jenkins_api('/queue/api/json?tree=items[id]')['text'])['items']
        jobs = jenkins_api('/api/json?tree=jobs[name,nextBuildNumber]')['text']
        write(folder / 'private-jenkins-before.json', json.loads(jobs))
        command = [sys.executable, str(ROOT / 'scripts/probe_nas_vm_capacity.py'), '--round', ROUND,
                   '--page-reporting-order', '0', '--target-hold-seconds', '60', '--resource-window', WINDOW]
        with (folder / 'capacity-stdout.log').open('xb') as output, (folder / 'capacity-stderr.log').open('xb') as error:
            process = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=error)
            while process.poll() is None:
                time.sleep(20)
                state = action(remote, 'status')
                write(folder / 'latest-window-state.json', state)
                if state['phase'] != 'paused':
                    raise RuntimeError('NAS watchdog ended the capacity window')
                idle()
        write(folder / 'capacity-process-result.json', {'exit_code': process.returncode})
        after_jobs = json.loads(jenkins_api('/api/json?tree=jobs[name,nextBuildNumber]')['text'])
        write(folder / 'private-jenkins-after.json', after_jobs)
        assert after_jobs == json.loads(jobs), 'An unexpected private Jenkins job started'
        if process.returncode == 0:
            qualification = capacity_evidence(BASE / ROUND)
            write(folder / 'capacity-evidence.json', qualification)
    finally:
        state = action(remote, 'restore')
        write(folder / 'restored-window.json', state)
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=20)
        recovered = verify_recovery(folder, remote)
        production = production_jobs()
        write(folder / 'production-after.json', production)
        after = infrastructure()
        write(folder / 'infrastructure-after.json', after)
        before = json.loads((folder / 'infrastructure-before.json').read_text())
        result = {'at': datetime.now(timezone.utc).isoformat(), 'maximum_window_seconds': 3600,
                  'all_seven_original_services_restored_healthy': True,
                  'restored_before_deadline': state['finished_at'] < state['deadline'],
                  'healthy_before_deadline': recovered['at_epoch'] < state['deadline'],
                  'native_jenkins_quiet': not production['active_builds'] and production['jobs'] ==
                      json.loads((folder / 'production-before.json').read_text())['jobs'],
                  'infrastructure_unchanged': all(before[k] == after[k] for k in
                      ('services', 'configuration_sha256', 'postgres_durability', 'comparison_driver_sha256')),
                  'controller_process_unchanged': before['states']['controller'] == after['states']['controller'],
                  'controller_no_new_oom': all(before['controller_memory']['memory.events'][key] ==
                      after['controller_memory']['memory.events'][key] for key in ('oom', 'oom_kill')),
                  'capacity_outcome': qualification['reason'] if qualification else 'missing_terminal_evidence',
                  'qualified_synthetic_capacity': bool(qualification and qualification['qualified_synthetic_capacity']),
                  'original_ci_dispatched': False, 'full_release_acceptance': False, 'production_ready': False}
        write(folder / 'window-result.json', result)
        print(json.dumps(result), flush=True)
        assert result['restored_before_deadline'] and result['healthy_before_deadline']
        assert result['native_jenkins_quiet'] and result['infrastructure_unchanged']
        assert result['controller_process_unchanged'] and result['controller_no_new_oom']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true', help='Write a reviewable local plan; no NAS actions')
    group.add_argument('--run-approved', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        PLAN.mkdir(exist_ok=True)
        target = PLAN / 'prepared-plan.json'
        plan = proposed_plan()
        if target.exists():
            assert json.loads(target.read_text()) == plan, 'Retain or explicitly review the previous plan'
        else:
            write(target, plan)
        print(json.dumps({'plan': str(target.relative_to(ROOT)), 'user_approved': False, 'nas_actions': False}))
    else:
        run()


if __name__ == '__main__':
    main()
