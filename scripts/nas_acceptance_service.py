"""Durable NAS coordinator. Unique systemd phase units survive the observer and Windows.

Known phase units are reconciled; neither a lost launch response nor a restart
can dispatch an original CI job twice. Every phase retains its independent guard.
"""
import os
import re
import subprocess
import sys
import time

import nas_native
import run_nas_day_window as day
from nas_progress import publish, read_json
from nas_ssh import ROOT

BASE = ROOT / 'test-results/nas-parity/followup'
ATTEMPT = os.environ.get('LEROY_ACCEPTANCE_ATTEMPT', 'v')
assert ATTEMPT in {'v', 'w', 'x', 'y'}
INSTANCE = os.environ.get('LEROY_ACCEPTANCE_INSTANCE', ATTEMPT)
assert re.fullmatch(re.escape(ATTEMPT) + r'(?:[2-9][0-9]*)?', INSTANCE)
PHASES = (('rust-jenkins',) if ATTEMPT == 'y' else ('release-leroy', 'release-jenkins') if ATTEMPT == 'x' else day.PHASES)
JOURNAL = BASE / ('nas-execution-20261017-' + INSTANCE)


def unit_name(phase):
    assert phase in day.PHASES
    # An admission that dispatched no CI can be corrected in a new immutable
    # operator, without reusing the first attempt's systemd invocation or journal.
    instance = INSTANCE if INSTANCE.startswith(ATTEMPT) else ATTEMPT
    return 'leroy-acceptance-20261017-' + instance + '-' + phase


def show(unit):
    response = subprocess.run(['systemctl', 'show', unit + '.service', '--property=LoadState',
                               '--property=ActiveState', '--property=SubState', '--property=ExecMainStatus',
                               '--property=InvocationID', '--property=ExecStart'], capture_output=True, timeout=15)
    return dict(line.split('=', 1) for line in response.stdout.decode().splitlines() if '=' in line)


def decision(retained, actual):
    """Pure crash-boundary decision; never replay an uncertain launch."""
    if actual.get('LoadState') == 'not-found':
        assert retained is None, 'Uncertain phase launch; reconcile rather than dispatch again'
        return 'launch'
    assert actual.get('LoadState') == 'loaded'
    assert retained is not None, 'Unjournaled phase unit must be inspected before adoption'
    if retained and retained.get('invocation_id'):
        assert actual['InvocationID'] == retained['invocation_id'], 'Phase unit was restarted externally'
    return 'observe'


def launch(phase, log):
    environment = ['--setenv=LEROY_NAS_NATIVE=1', '--setenv=PYTHONPATH=' + str(ROOT / 'vendor'),
                   '--setenv=PATH=' + str(ROOT / 'bin') + ':/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin']
    command = ['systemd-run', '--unit=' + unit_name(phase), '--property=Type=exec',
               '--property=RemainAfterExit=yes', '--property=Restart=no', '--property=Slice=leroyparity.slice',
               '--property=MemoryMax=' + ('1G' if ATTEMPT == 'x' else '192M'), '--property=MemorySwapMax=0', '--property=CPUQuota=50%',
               '--property=Nice=10', '--property=StandardOutput=append:' + str(log),
               '--property=StandardError=append:' + str(log), *environment,
               '/usr/bin/python3', '-B', str(ROOT / 'scripts/run_nas_day_window.py'),
               '--attempt', ATTEMPT, '--phase', phase, '--run-approved']
    if ATTEMPT == 'y':
        command.append('--diagnostic-reference')
    result = subprocess.run(command, capture_output=True, timeout=30)
    assert result.returncode == 0, 'Phase launch result requires reconciliation'


def verify_closed(phase):
    folder = BASE / day.window_name(phase)
    result = read_json(folder / 'window-result.json')
    assert result['phase'] == phase and result['outcome'] == 'original_stage_collected'
    assert all(result[k] is True for k in ('all_seven_original_services_restored_healthy',
               'healthy_before_deadline', 'native_jenkins_quiet', 'infrastructure_unchanged',
               'controller_process_unchanged', 'controller_no_new_oom'))
    archive = read_json(folder / 'closed-disk-archive.json')
    assert archive['source_removed'] and archive['copy_sha256'] == archive['sha256']
    if phase.startswith('rust-'):
        assert result['original_rust_qualified'] is True
        if ATTEMPT == 'y':
            from run_nas_full_release_window import require_rust_evidence

            assert result['diagnostic_reference_only'] is True
            require_rust_evidence(BASE / day.round_name(phase), 'jenkins')
        else:
            day.require_day_rust(phase.rsplit('-', 1)[1])


def recorder(phase, approval):
    case = BASE / day.round_name(phase)
    marker = case / 'leroy-start.json'
    if phase.endswith('jenkins') or not marker.exists():
        return
    run_id = read_json(marker)['id']
    trace_intent = case / 'persistent-control-trace-intent.json'
    if not trace_intent.exists():
        from nas_worker_control_trace import start_worker_trace

        publish(trace_intent, {'run_id': run_id, 'at_epoch': time.time()})
        start_worker_trace(case, run_id,
                          'sha256:b345787854eb274f0fd8eea428882ec4bacf560cca5cacefd3b7e4fbb63a7d1c',
                          approval['absolute_deadline_epoch'])
    unit = unit_name(phase) + '-lease'
    if show(unit).get('LoadState') != 'not-found':
        return
    # Retain intent before launch; a failed response is not a reason to create a
    # second log reader or another CI run.
    intent = case / 'persistent-lease-recorder-intent.json'
    if intent.exists():
        return
    publish(intent, {'unit': unit, 'at_epoch': time.time()})
    result = subprocess.run(['systemd-run', '--unit=' + unit, '--property=Type=exec',
        '--property=RemainAfterExit=yes', '--property=Slice=leroyparity.slice', '--property=MemoryMax=64M',
        '--property=MemorySwapMax=0', '--property=Nice=10', '--setenv=LEROY_NAS_NATIVE=1',
        '--setenv=PYTHONPATH=' + str(ROOT / 'vendor'), '/usr/bin/python3', '-B',
        str(ROOT / 'scripts/nas_lease_recorder.py'), '--run', run_id, '--folder', str(case),
        '--deadline', str(approval['absolute_deadline_epoch'] - 900)], capture_output=True, timeout=30)
    publish(case / 'persistent-lease-recorder-launch.json', {'unit': unit, 'launched': result.returncode == 0})


def run():
    assert nas_native.enabled()
    nas_native.validate(ROOT)
    day.configure_attempt(ATTEMPT)
    day.DIAGNOSTIC_REFERENCE = ATTEMPT == 'y'
    JOURNAL.mkdir(exist_ok=True)
    state_file = JOURNAL / 'state.json'
    state = read_json(state_file) if state_file.exists() else {'status': 'running', 'completed': [], 'phases': {}}
    if state['status'] in {'stopped', 'complete'}:
        return
    try:
        for phase in PHASES:
            if phase in state['completed']:
                verify_closed(phase)
                continue
            retained = state['phases'].get(phase)
            actual = show(unit_name(phase))
            operation = decision(retained, actual)
            plan = BASE / ('day-window-plan-20261015-' + ATTEMPT + '-' + phase) / 'approval.json'
            if operation == 'launch':
                if not plan.exists():
                    day.prerequisites(phase)
                    day.prepare(phase)
                approval = read_json(plan)
                day.validate_approval(approval)
                state['phases'][phase] = {'launch_intent': True, 'unit': unit_name(phase)}
                publish(state_file, state)
                try:
                    launch(phase, JOURNAL / (phase + '.log'))
                except (subprocess.TimeoutExpired, OSError, AssertionError):
                    # The unique unit may already exist. Observe it; do not run
                    # systemd-run again after an uncertain launch response.
                    state['phases'][phase]['launch_response_unknown'] = True
                    publish(state_file, state)
                actual = show(unit_name(phase))
                decision(state['phases'][phase], actual)
            assert str(ROOT / 'scripts/run_nas_day_window.py') in actual.get('ExecStart', '')
            assert '--phase ' + phase in actual.get('ExecStart', '')
            state['phases'][phase] = {'unit': unit_name(phase), 'invocation_id': actual['InvocationID']}
            state['current_phase'] = phase
            publish(state_file, state)
            approval = read_json(plan)
            while True:
                try:
                    actual = show(unit_name(phase))
                except (subprocess.TimeoutExpired, OSError) as error:
                    publish(JOURNAL / (phase + '-read-gap.json'),
                            {'at_epoch': time.time(), 'error_type': type(error).__name__, 'ci_restarted': False})
                    assert time.time() < approval['absolute_deadline_epoch'] + 900
                    time.sleep(5)
                    continue
                decision(state['phases'][phase], actual)
                if actual.get('SubState') in {'exited', 'failed', 'dead'}:
                    break
                assert time.time() < approval['absolute_deadline_epoch'] + 900, 'Independent guard recovery must be inspected'
                try:
                    recorder(phase, approval)
                except (subprocess.TimeoutExpired, OSError, ValueError, AssertionError) as error:
                    # Supplementary telemetry cannot decide the original CI run.
                    publish(JOURNAL / (phase + '-recorder-gap.json'),
                            {'at_epoch': time.time(), 'error_type': type(error).__name__, 'ci_restarted': False})
                time.sleep(10)
            case = BASE / day.round_name(phase)
            if (case / 'worker-control-trace.json').exists() and not (case / 'worker-control-trace').exists():
                try:
                    from nas_worker_control_trace import collect_worker_trace

                    collect_worker_trace(case)
                except (subprocess.TimeoutExpired, OSError, ValueError, AssertionError) as error:
                    publish(JOURNAL / (phase + '-trace-collection-gap.json'),
                            {'at_epoch': time.time(), 'error_type': type(error).__name__})
            assert actual.get('ExecMainStatus') == '0', 'Retain failed original phase; no implicit retry'
            verify_closed(phase)
            state['completed'].append(phase)
            publish(state_file, state)
        if ATTEMPT == 'y':
            state.update(status='complete', diagnostic_reference_only=True, full_release_acceptance=False,
                         production_ready=False, production_cutover=False)
            publish(state_file, state)
            return
        report = read_json(BASE / day.round_name('release-leroy') / 'analysis.json')
        complete = report['all_29_original_group_receipts_present_both'] and report['all_29_original_groups_executed_both']
        named = False
        if complete:
            case = BASE / day.round_name('release-leroy')
            with (JOURNAL / 'named-outcome-analysis.log').open('xb') as log:
                result = subprocess.run([sys.executable, str(ROOT / 'scripts/compare_nas_original_test_outcomes.py'),
                                         '--folder', case.relative_to(ROOT).as_posix()], stdout=log,
                                        stderr=subprocess.STDOUT, timeout=120)
            assert result.returncode == 0
            named = read_json(case / 'original-test-outcome-comparison.json')['same_recorded_named_outcomes_both']
        state.update(status='complete', original_workloads_successful_both=report['all_original_workloads_successful_both'],
                     complete_original_inventories_both=complete, same_recorded_named_outcomes_both=named,
                     production_ready=False, production_cutover=False)
    except Exception as error:
        state.update(status='stopped', error_type=type(error).__name__, original_ci_restarted=False,
                     production_cutover=False, recovery_owned_by_independent_nas_guard=True)
    publish(state_file, state)


if __name__ == '__main__':
    os.umask(0o077)
    run()
