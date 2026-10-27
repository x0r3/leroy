"""Original Graphato comparison within the separately authorized fixed night end.

Synthetic worst-case capacity remains unqualified unless its actual proof passed.
Earlier trials require successful standalone Rust; E runs both complete original
releases directly. F retains E and attempts only its undispatched Jenkins reference
after production overlap ended E. No source/test/fixture changes.
"""

import argparse
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

import nas_release_vm as vm
from diagnose_nas_release_group import observe_control, observe_owned_jobs
from nas_followup_support import production_jobs
from nas_gitea_target import idle
from nas_optional_observer import collect_optional_trace
from nas_ssh import ROOT
from run_nas_capacity_window import capacity_evidence, prepare_on_nas
from run_nas_full_release_window import (
    SERVICES,
    action,
    infrastructure,
    require_rust_evidence,
    verify_recovery,
)
from run_nas_night_window import DEADLINE, register_runs, stop_private_jenkins
from run_nas_night_window import SOURCES as NIGHT_SOURCES

WINDOW = 'resource-window-original-night-20261014'
BASE = ROOT / 'test-results/nas-parity/followup'
PLAN = BASE / 'original-night-window-plan-20261014'
ROUNDS = ['original-night-rust-leroy-20261014', 'original-night-rust-jenkins-20261014',
          'original-night-release-20261014']
SOURCES = (*NIGHT_SOURCES, 'scripts/run_nas_original_night_window.py', 'scripts/nas_optional_observer.py')
ATTEMPT = 'a'


def configure_attempt(attempt):
    global WINDOW, PLAN, ROUNDS, ATTEMPT
    assert attempt in {'a', 'b', 'c', 'd', 'e', 'f'}
    ATTEMPT = attempt
    suffix = '' if attempt == 'a' else '-' + attempt
    WINDOW = 'resource-window-original-night-20261014' + suffix
    PLAN = BASE / ('original-night-window-plan-20261014' + suffix)
    prefix = 'original-night-' if attempt == 'a' else 'original-night-' + attempt + '-'
    ROUNDS = [prefix + 'rust-leroy-20261014', prefix + 'rust-jenkins-20261014', prefix + 'release-20261014']
    if attempt in {'e', 'f'}:
        ROUNDS = [prefix + 'release-20261014']
    if attempt == 'f':
        ROUNDS = ['original-night-e-release-20261014']


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    temporary = path.with_suffix(path.suffix + '.partial')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def proposed_plan():
    profile, assessment = select_profile()
    proofs = [BASE / ('night-capacity' + str(high) + '-20261014') / name
              for high in (3584, 3840, 4096) for name in
              ('final-state.json', 'phases.json', 'leroy-memory-summary.json',
               'production-measurement-qualification-synthetic-capacity.json')]
    if ATTEMPT in {'c', 'd', 'e', 'f'}:
        proofs += [BASE / 'original-night-b-rust-jenkins-20261014' / name for name in
                   ('owned-vm-resource-guard.json', 'owned-vm-shutdown.json', 'jenkins-memory-summary.json', 'final-state.json')]
        proofs.append(BASE / 'resource-window-original-night-20261014-b/window-result.json')
    sources = SOURCES
    if ATTEMPT in {'c', 'd', 'e', 'f'}:
        sources = (*sources, 'src/leroy/lease_trace.py', 'scripts/observe_nas_release_jobs.py',
                   'scripts/nas_worker_control_trace.py', 'scripts/qualify_nas_worker_transport.py',
                   'scripts/deploy_nas_worker_transport.py', 'scripts/qualify_nas_runner_cadence.py',
                   'scripts/deploy_nas_runner_cadence.py')
    plan = {'user_approved': False, 'window': WINDOW, 'maximum_window_seconds': 36000,
            'absolute_deadline_epoch': DEADLINE, 'restore_margin_seconds': 900,
            'services': list(SERVICES), 'comparison_rounds': ROUNDS, 'source_commit': vm.COMMIT,
            'application_sources_tests_and_fixture_limits_unchanged': True,
            'synthetic_maximum_required_for_bounded_original_trial': False,
            'successful_original_rust_required_both_engines_for_full_release': True,
            'resource_profile': profile, 'page_reporting_order': 0, 'early_memory_pressure': True,
            'synthetic_maximum_qualified': assessment['synthetic_maximum_qualified'],
            'supporting_proof_sha256': {p.relative_to(ROOT).as_posix(): vm.digest(p) for p in proofs},
            'native_jenkins_changed': False, 'production_cutover': False,
            'script_sha256': {name: vm.digest(ROOT / name) for name in sources}}
    if ATTEMPT in {'c', 'd', 'e', 'f'}:
        deployed = read(BASE / 'worker-transport-candidate-20261014/deployment-proof.json')
        assert deployed['exact_linux_qualified_image_deployed'] and deployed['linux_worker_tests'] == 28
        assert deployed['request_timeouts_or_retries_changed'] is False
        runner = read(BASE / 'runner-cadence-completion-20261015/deployment-proof.json')
        assert runner['exact_linux_qualified_image_deployed'] and runner['linux_runner_tests'] == 23
        assert runner['only_maintain_lease_function_changed'] and runner['only_compose_runner_image_changed']
        runner_proof = BASE / 'runner-cadence-completion-20261015/deployment-proof.json'
        plan['supporting_proof_sha256'][runner_proof.relative_to(ROOT).as_posix()] = vm.digest(runner_proof)
        plan.update(diagnostic_worker_image=deployed['worker_image'], diagnostic_worker_trace_enabled=True,
                    corrected_runner_image=runner['runner_image'],
                    worker_process_and_read_only_sql_observers=True,
                    earlier_comparison_window_closed='resource-window-original-night-20261014-b',
                    reason='Measured RAM reserve undershoot with 4096 MiB memory.high; retain 8 GiB guest and all original fixture limits, use 3584 MiB memory.high')
    if ATTEMPT in {'d', 'e', 'f'}:
        path = BASE / 'engine-storage-20261015-b/deployment-proof.json'
        storage = read(path)
        assert storage['qualified_worker_image_config_and_layers_unchanged'] and storage['linux_worker_tests'] == 28
        assert storage['worker_image'] == deployed['worker_image'] and storage['old_engine_root_retained']
        assert storage['source_service_configuration_unchanged_except_snapshot_image_reference']
        more = [BASE / 'original-night-c-rust-leroy-20261014' / name for name in
                ('owned-vm-resource-guard.json', 'owned-vm-shutdown.json', 'leroy-memory-summary.json', 'final-state.json')]
        more += [BASE / 'resource-window-original-night-20261014-c/window-result.json', path]
        plan['supporting_proof_sha256'].update({p.relative_to(ROOT).as_posix(): vm.digest(p) for p in more})
        source = 'scripts/initialize_nas_ssd_engine.py'
        plan['script_sha256'][source] = vm.digest(ROOT / source)
        plan.update(earlier_comparison_window_closed='resource-window-original-night-20261014-c',
                    ssd_worker_runtime_root=storage['engine_root'], existing_named_volumes_reused=True,
                    reason='Use the intermediate 3840 MiB resident VM budget after measured RAM/swap stops; place unchanged worker image on SSD after observed Btrfs runtime reads; preserve original sources/tests/fixture limits')
    if ATTEMPT in {'e', 'f'}:
        plan.update(successful_original_rust_required_both_engines_for_full_release=False,
                    original_rust_checks_required_inside_complete_release=True,
                    additional_standalone_rust_jobs=False,
                    earlier_comparison_window_closed='resource-window-original-night-20261014-d',
                    reason='Execute both complete unchanged original release pipelines, including their Rust checks, after verified pool identity preflight; no duplicate standalone Rust qualification jobs')
        path = BASE / 'resource-window-original-night-20261014-d/window-result.json'
        plan['supporting_proof_sha256'][path.relative_to(ROOT).as_posix()] = vm.digest(path)
        source = 'scripts/nas_test_environment.py'
        plan['script_sha256'][source] = vm.digest(ROOT / source)
    if ATTEMPT == 'f':
        path = BASE / 'resource-window-original-night-20261014-e/window-result.json'
        assert read(path)['all_seven_original_services_restored_healthy']
        plan['supporting_proof_sha256'][path.relative_to(ROOT).as_posix()] = vm.digest(path)
        validation = PLAN / 'guard-linux-validation.json'
        proof = read(validation)
        assert proof['real_linux_proc_identity_verified'] and proof['actual_signals_sent'] is False
        assert proof['source_sha256'] == vm.digest(ROOT / 'scripts/nas_resource_window_guard.py')
        plan['supporting_proof_sha256'][validation.relative_to(ROOT).as_posix()] = vm.digest(validation)
        plan.update(earlier_comparison_window_closed='resource-window-original-night-20261014-e',
                    engines_to_dispatch=['jenkins'], retain_original_interrupted_leroy=True,
                    complete_original_comparison_already_proven=False,
                    minimum_full_stage_remaining_seconds=6600, restore_margin_seconds=900,
                    full_completion_within_remaining_time_guaranteed=False,
                    reason='Productive music job244 ended E; retain its interrupted Leroy run, archive its closed disk, attempt only the original undispatched Jenkins reference within the same fixed overnight end')
    return plan


def require_approval():
    assert (PLAN / 'approval.json').is_file(), 'Explicit overnight authorization must be recorded'
    value = read(PLAN / 'approval.json')
    assert value['user_approved'] is True and value['explicit_user_request'].strip()
    assert all(value[key] == expected for key, expected in proposed_plan().items() if key != 'user_approved'), \
        'Original night scope or source changed; retain the approved version'
    return value


def select_profile():
    evidence = []
    for high in (3584, 3840, 4096):
        case = BASE / ('night-capacity' + str(high) + '-20261014')
        value = capacity_evidence(case)
        assert value['reason'] in {'conservative_host_admission_declined', 'synthetic_target_held'}
        summary = value['memory_summary']
        assert summary['minimum_host_available_kib'] >= 128 * 1024
        assert summary['minimum_host_swap_free_kib'] >= 2304 * 1024
        assert summary['guest_oom_kill_counters'] == [0] and summary['physical_nas_oom_kill_counters'] == [3]
        assert read(case / 'production-measurement-qualification-synthetic-capacity.json')['native_jenkins_quiet_window_verified']
        evidence.append({'profile': 'nas-8g-ssd-soft-ram-' + str(high), **value})
    usable = [v for v in evidence if v['peak_allocated_mib'] >= 5120 and
              v['memory_summary']['minimum_host_available_kib'] >= 256 * 1024]
    assert usable, 'No supporting capacity with sufficient observed NAS reserve'
    if ATTEMPT in {'c', 'd', 'e', 'f'}:
        case = BASE / 'original-night-b-rust-jenkins-20261014'
        assert read(case / 'final-state.json')['original_ci_terminal']
        guard = read(case / 'owned-vm-resource-guard.json')['resource_guard']
        assert guard['host_memory_kib']['MemAvailable'] < guard['minimum_host_memory_kib']['MemAvailable']
        high = 3840 if ATTEMPT in {'d', 'e', 'f'} else 3584
        if ATTEMPT in {'d', 'e', 'f'}:
            swap = read(BASE / 'original-night-c-rust-leroy-20261014/owned-vm-resource-guard.json')['host_memory_kib']
            assert swap['SwapFree'] < 2304 * 1024 and swap['MemAvailable'] > 512 * 1024
        best = next(v for v in usable if v['profile'] == 'nas-8g-ssd-soft-ram-' + str(high))
    else:
        best = max(usable, key=lambda v: (v['peak_allocated_mib'], v['memory_summary']['minimum_host_available_kib']))
    return best['profile'], {'supporting_probes': evidence, 'selected_profile': best['profile'],
            'synthetic_maximum_qualified': any(v['qualified_synthetic_capacity'] for v in evidence),
            'original_workload_qualified': False,
            'decision': 'Measure the actual original workload within unchanged NAS guards; no extrapolated success'}


def stage(folder, remote, label, arguments, *, case=None, minimum_remaining=1800):
    require_approval()
    state = action(remote, 'status')
    assert state['phase'] == 'paused' and state['deadline'] == DEADLINE
    assert DEADLINE - time.time() >= minimum_remaining + 900
    idle()
    assert not (folder / (label + '-started.json')).exists(), 'Observe the retained dispatch; never repeat it'
    process = None
    with (folder / (label + '-stdout.log')).open('xb') as out, (folder / (label + '-stderr.log')).open('xb') as err:
        try:
            process = subprocess.Popen([sys.executable, *arguments], cwd=ROOT, stdout=out, stderr=err)
            write(folder / (label + '-started.json'), {'pid': process.pid, 'at_epoch': time.time(), 'original_ci_restarted': False})
            while process.poll() is None:
                if case is not None:
                    register_runs(remote, case)
                    if ATTEMPT in {'c', 'd', 'e', 'f'} and label in {'rust-leroy', 'full-release-leroy'} and (case / 'leroy-start.json').exists() and not (case / 'worker-control-trace-starting.json').exists():
                        from nas_worker_control_trace import start_worker_trace

                        candidate = read(BASE / 'worker-transport-candidate-20261014/deployment-proof.json')['worker_image']
                        write(case / 'worker-control-trace-starting.json', {'run_id': read(case / 'leroy-start.json')['id'],
                                                                          'optional_observation': True})
                        try:
                            start_worker_trace(case, read(case / 'leroy-start.json')['id'], candidate, DEADLINE)
                        except (AssertionError, RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
                            write(case / 'worker-control-trace-start-error.json', {'error_type': type(error).__name__,
                                  'original_ci_restarted': False, 'observer_start_outcome_uncertain': True})
                state = action(remote, 'register-vm' if case is not None else 'status')
                write(folder / 'latest-window-state.json', state)
                assert state['phase'] == 'paused' and time.time() < DEADLINE - 900
                time.sleep(10)
            if case is not None:
                register_runs(remote, case)
            write(folder / (label + '-result.json'), {'exit_code': process.returncode, 'at_epoch': time.time()})
            if case is not None:
                collect_optional_trace(case)
            assert process.returncode == 0, 'Retain the failed or uncertain original stage'
        finally:
            if process is not None and process.poll() is None:
                action(remote, 'restore')
                process.terminate()
                process.wait(timeout=20)


def archive(folder, remote, name, engine):
    stage(folder, remote, 'archive-' + name + '-' + engine,
          [str(ROOT / 'scripts/archive_nas_night_disk.py'), '--round', name, '--engine', engine, '--resource-window', WINDOW])


def full_release_allowed(qualified):
    return set(qualified) == {'leroy', 'jenkins'} and all(value is True for value in qualified.values())


def run():
    require_approval()
    if ATTEMPT == 'f':
        previous = read(BASE / 'resource-window-original-night-20261014-e/window-result.json')
        assert previous['all_seven_original_services_restored_healthy']
        assert not (BASE / ROUNDS[-1] / 'jenkins-start.json').exists(), 'Never redispatch the retained Jenkins run'
    assert read(BASE / 'resource-window-night-20261014/window-result.json')['all_seven_original_services_restored_healthy']
    if ATTEMPT in {'c', 'd', 'e', 'f'}:
        assert read(BASE / 'resource-window-original-night-20261014-b/window-result.json')['all_seven_original_services_restored_healthy']
    if ATTEMPT in {'d', 'e', 'f'}:
        assert read(BASE / 'resource-window-original-night-20261014-c/window-result.json')['all_seven_original_services_restored_healthy']
    if ATTEMPT in {'e', 'f'}:
        assert read(BASE / 'resource-window-original-night-20261014-d/window-result.json')['all_seven_original_services_restored_healthy']
    profile, decision = select_profile()
    folder = BASE / WINDOW
    assert not folder.exists(), 'Never reopen the previous journal'
    folder.mkdir()
    write(folder / 'capacity-assessment.json', decision)
    remote = '/volume1/docker/leroy-nas-parity/' + WINDOW
    prepare_on_nas(folder, remote, overnight='original')
    outcome = 'not_completed'
    stopped = threading.Event()
    observers = []
    try:
        write(folder / 'paused.json', action(remote, 'pause'))
        qualified = {}
        for index, engine in enumerate(() if ATTEMPT in {'e', 'f'} else ('leroy', 'jenkins')):
            case = BASE / ROUNDS[index]
            stage(folder, remote, 'rust-' + engine, [str(ROOT / 'scripts/diagnose_nas_release_group.py'),
                  '--folder', case.relative_to(ROOT).as_posix(), '--engine', engine, '--group', 'server-test',
                  '--resource-profile', profile, '--postgres-init', '--memory-trace',
                  '--page-reporting-order', '0', '--early-memory-pressure'], case=case, minimum_remaining=4500)
            try:
                if ATTEMPT in {'c', 'd', 'e', 'f'} and engine == 'leroy':
                    assert read(case / 'leroy-run.json')['image_digest'] == read(BASE / 'worker-transport-candidate-20261014/deployment-proof.json')['worker_image']
                evidence = require_rust_evidence(case, engine)
            except AssertionError:
                evidence = None
            qualified[engine] = evidence is not None
            write(folder / (engine + '-rust-assessment.json'), {'qualified': qualified[engine], 'evidence': evidence})
            summary = read(case / (engine + '-memory-summary.json'))
            assert summary['minimum_host_available_kib'] >= 128 * 1024 and summary['minimum_host_swap_free_kib'] >= 2304 * 1024, \
                'Investigate an observed NAS reserve undershoot before adding more original load'
            archive(folder, remote, case.name, engine)
        write(folder / 'original-rust-decision.json', {'engines': qualified,
              'standalone_rust_qualified_both_engines': full_release_allowed(qualified),
              'original_rust_required_inside_full_release': ATTEMPT in {'e', 'f'},
              'full_release_dispatch_basis': 'unchanged_complete_original_pipeline_includes_rust' if ATTEMPT in {'e', 'f'} else 'two_successful_standalone_rust_jobs'})
        if ATTEMPT not in {'e', 'f'} and not full_release_allowed(qualified):
            outcome = 'original_rust_comparison_collected_without_two_successes'
            return
        observers = [threading.Thread(target=observe_control, args=(folder, stopped), daemon=True),
                     threading.Thread(target=observe_owned_jobs, args=(folder, stopped), daemon=True)]
        for observer in observers:
            observer.start()
        if ATTEMPT == 'f':
            archive(folder, remote, ROUNDS[-1], 'leroy')
        for engine in (('jenkins',) if ATTEMPT == 'f' else ('leroy', 'jenkins')):
            case = BASE / ROUNDS[-1]
            stage(folder, remote, 'full-release-' + engine,
                  [str(ROOT / 'scripts/compare_nas_full_release.py'), '--folder', case.relative_to(ROOT).as_posix(),
                   '--engine', engine, '--first-engine', 'leroy', '--resource-profile', profile,
                   '--postgres-init', '--memory-trace', '--page-reporting-order', '0', '--early-memory-pressure'],
                  case=case, minimum_remaining=6600 if ATTEMPT == 'f' else 8100)
            idle()
            vm.stop()
            stop_private_jenkins()
            collect_optional_trace(case)
            if ATTEMPT == 'f' and DEADLINE - time.time() < 2700:
                write(folder / 'closed-disk-archive-deferred.json', {
                    'round': case.name, 'engine': engine, 'closed_disk_retained_on_ssd': True,
                    'reason': 'Preserve service recovery margin; original CI results remain retained'})
            else:
                archive(folder, remote, case.name, engine)
        outcome = 'jenkins_reference_collected_after_interrupted_leroy' if ATTEMPT == 'f' else 'original_full_release_comparison_collected'
    except Exception as error:
        outcome = 'stopped:' + type(error).__name__
        write(folder / 'operation-error.json', {'type': type(error).__name__, 'original_ci_restarted': False})
        raise
    finally:
        state = action(remote, 'restore')
        write(folder / 'restored-window.json', state)
        stopped.set()
        for observer in observers:
            observer.join(timeout=30)
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
                  'synthetic_maximum_qualified': decision['synthetic_maximum_qualified'],
                  'production_cutover': False, 'production_ready': False}
        write(folder / 'window-result.json', result)
        print(json.dumps(result), flush=True)
        assert all(result[k] for k in ('restored_before_deadline', 'healthy_before_deadline', 'native_jenkins_quiet',
                   'infrastructure_unchanged', 'controller_process_unchanged', 'controller_no_new_oom'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--run-approved', action='store_true')
    parser.add_argument('--attempt', choices=('a', 'b', 'c', 'd', 'e', 'f'), default='a')
    args = parser.parse_args()
    configure_attempt(args.attempt)
    assert args.prepare != args.run_approved
    if args.prepare:
        PLAN.mkdir(exist_ok=True)
        assert not (PLAN / 'prepared-plan.json').exists()
        write(PLAN / 'prepared-plan.json', proposed_plan())
        print(json.dumps({'plan': str((PLAN / 'prepared-plan.json').relative_to(ROOT)), 'nas_actions': False}))
    else:
        run()


if __name__ == '__main__':
    main()
