"""Separate bounded day windows: original Rust qualification, then full releases."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone

import nas_release_vm as vm
from nas_followup_support import production_jobs
from nas_gitea_target import idle
from nas_ssh import ROOT
from run_nas_capacity_window import prepare_on_nas
from run_nas_full_release_window import (
    SERVICES,
    action,
    infrastructure,
    require_rust_evidence,
    verify_recovery,
)
from run_nas_night_window import SOURCES as NIGHT_SOURCES
from run_nas_night_window import register_runs, stop_private_jenkins

BASE = ROOT / 'test-results/nas-parity/followup'
DAY_END = datetime.fromisoformat('2026-10-15T23:59:59+02:00').timestamp()
CONTINUATION_END = datetime.fromisoformat('2026-10-16T23:59:59+02:00').timestamp()
CONTINUATION_REQUEST = 'Zwischenhinweis, dein Arbeitsfenster ist noch für den gesamten morgigen Tag freigegeben'
PHASES = ('rust-leroy', 'rust-jenkins', 'release-leroy', 'release-jenkins')
ATTEMPT = 'a'
DIAGNOSTIC_REFERENCE = False
ATTEMPTS = ('a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y')
MATCHED_ATTEMPTS = set(ATTEMPTS) - {'a'}
SOURCES = (*NIGHT_SOURCES, 'scripts/run_nas_day_window.py', 'scripts/archive_nas_day_disk.py',
           'scripts/nas_vm_guest_swap.py', 'scripts/nas_optional_observer.py', 'scripts/nas_test_environment.py',
           'scripts/nas_ci_background.py', 'scripts/nas_vm_file_memory.py', 'scripts/nas_vm_file_capacity.py',
           'scripts/nas_followup_support.py', 'scripts/nas_verified_container.py', 'scripts/nas_vm_capacity_reference.py')
SOURCES += ('scripts/deploy_nas_control_working_set.py', 'scripts/deploy_nas_engine_memory.py')
SOURCES += ('scripts/nas_native.py', 'scripts/nas_open_authorization.py', 'scripts/nas_acceptance_service.py',
            'scripts/nas_lease_recorder.py', 'scripts/nas_source_git.py', 'scripts/nas_ssh.py',
            'scripts/observe_nas_release_jobs.py')
SOURCES += ('scripts/deploy_nas_parity.py', 'scripts/nas_worker_control_trace.py', 'scripts/probe_nas_resident_control.py')
SOURCES += ('scripts/nas_capacity_agent.py', 'scripts/nas_vm_capacity_local.py')
SOURCES += ('scripts/compare_nas_antares.py',)
SOURCES += ('scripts/nas_failed_w_reference.py', 'scripts/nas_rust_reference.py', 'scripts/nas_console_binding.py', 'scripts/qualify_nas_console_logging.py',
            'scripts/probe_nas_console_pipe.py', 'scripts/deploy_nas_console_logging.py',
            'src/leroy/console_logging.py', 'src/leroy/server.py')
SOURCES += ('scripts/nas_original_workload.py', 'scripts/nas_graphato_transport.py', 'src/leroy/actions.py', 'scripts/nas_vm_dns.py', 'scripts/nas_progress.py')


def read(path):
    from nas_progress import read_json

    return read_json(path)


def write(path, value):
    assert not path.exists(), 'Retain the first observation: ' + path.name
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def configure_attempt(attempt):
    global ATTEMPT
    assert attempt in ATTEMPTS
    ATTEMPT = attempt


def window_name(phase, attempt=None):
    assert phase in PHASES
    attempt = ATTEMPT if attempt is None else attempt
    assert attempt in ATTEMPTS
    if attempt in {'v', 'w', 'x', 'y'}:
        return 'resource-window-acceptance-20261017-' + attempt + '-' + phase
    return 'resource-window-day-20261015-' + ('' if attempt == 'a' else attempt + '-') + phase


def round_name(phase, attempt=None):
    assert phase in PHASES
    attempt = ATTEMPT if attempt is None else attempt
    assert attempt in ATTEMPTS
    if attempt in {'v', 'w', 'x', 'y'}:
        return 'acceptance-20261017-' + attempt + '-' + phase if phase.startswith('rust-') else 'acceptance-20261017-' + attempt + '-release'
    prefix = 'day-' if attempt == 'a' else 'day-' + attempt + '-'
    return prefix + phase + '-20261015' if phase.startswith('rust-') else prefix + 'release-20261015'


def resource_profile(attempt):
    assert attempt in ATTEMPTS
    return {'a': vm.GUEST_SWAP_PROFILE, 'b': vm.BOUNDED_GUEST_SWAP_PROFILE, 'c': vm.FILE_MEMORY_PROFILE,
            'd': vm.PROTECTED_FILE_MEMORY_PROFILE, 'e': vm.PROTECTED_FILE_MEMORY_PROFILE, 'f': vm.PROTECTED_FILE_MEMORY_PROFILE,
            'g': vm.DISK_QOS_FILE_MEMORY_PROFILE, 'h': vm.DISK_QOS_FILE_MEMORY_PROFILE,
            'i': vm.DISK_QOS_FILE_MEMORY_PROFILE, 'j': vm.DISK_QOS_FILE_MEMORY_PROFILE,
            'k': vm.DISK_QOS_FILE_MEMORY_PROFILE, 'l': vm.DISK_QOS_FILE_MEMORY_PROFILE,
            'm': vm.DISK_QOS_FILE_MEMORY_PROFILE, 'n': vm.DISK_QOS_FILE_MEMORY_PROFILE,
            'o': vm.DISK_QOS_FILE_MEMORY_PROFILE, 'p': vm.DISK_QOS_FILE_MEMORY_PROFILE, 'q': vm.DISK_QOS_FILE_MEMORY_PROFILE, 'r': vm.DISK_QOS_FILE_MEMORY_PROFILE, 's': vm.DISK_QOS_FILE_MEMORY_PROFILE, 't': vm.DISK_QOS_FILE_MEMORY_PROFILE, 'u': vm.DISK_QOS_FILE_MEMORY_PROFILE, 'v': vm.DISK_QOS_FILE_MEMORY_PROFILE, 'w': vm.DISK_QOS_FILE_MEMORY_PROFILE, 'x': vm.DISK_QOS_FILE_MEMORY_PROFILE, 'y': vm.DISK_QOS_FILE_MEMORY_PROFILE}[attempt]


def page_reporting_order(attempt):
    assert attempt in ATTEMPTS
    return 4 if attempt in {'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'} else 0


def authorization_end(attempt):
    assert attempt in ATTEMPTS
    if attempt in {'v', 'w', 'x', 'y'}:
        return None
    return CONTINUATION_END if attempt in {'m', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'} else DAY_END


def maximum_window_seconds(attempt):
    assert attempt in ATTEMPTS
    return 43200 if attempt == 'x' else 14400


def open_authorization_binding(attempt=None):
    from nas_open_authorization import binding

    return binding(maximum_window_seconds=maximum_window_seconds(ATTEMPT if attempt is None else attempt))


def continuation_binding():
    path = BASE / 'authorization-continuation-20261016.json'
    proof = read(path)
    assert proof['explicit_user_request'] == CONTINUATION_REQUEST
    assert proof['interpreted_date'] == '2026-10-16' and proof['timezone'] == 'Europe/Berlin'
    assert proof['additional_authorization_end_epoch'] == CONTINUATION_END
    assert proof['services'] == list(SERVICES) and proof['maximum_separate_window_seconds'] == 14400
    assert proof['restore_margin_seconds'] == 900 and proof['no_production_cutover'] is True
    assert proof['current_l_fixed_deadline_unchanged_epoch'] == DAY_END
    return {'authorization_sha256': vm.digest(path), 'end_epoch': CONTINUATION_END,
            'closed_and_current_old_windows_extended': False}


def local_capacity_binding(attempt='m'):
    assert attempt in {'m', 'n', 'o'}
    name, count = {'m': ('nas-local-capacity-qualification-20261015', 18),
                   'n': ('nas-local-capacity-qualification-20261015-c', 29),
                   'o': ('nas-local-capacity-qualification-20261015-e', 41)}[attempt]
    folder = BASE / name
    proof = read(folder / 'linux-validation.json')
    assert proof['all_passed'] is True and proof['native_linux_tests'] == count and proof['failures_or_skips'] == 0
    assert proof['vm_started'] is proof['memory_load_started'] is proof['guest_ssh_requests'] is False
    resources = proof['driver_resources']
    assert resources['memory.low'] == str(32 * 1024**2) and resources['memory.max'] == str(128 * 1024**2)
    assert resources['memory.min'] == resources['memory.swap.max'] == '0'
    assert resources['cpu.max'] == '50000 100000' and resources['pids.max'] == '64'
    assert resources['global_settings_changed'] is False
    archive = folder / 'inputs.zip'
    assert vm.digest(archive) == proof['inputs_sha256']
    with zipfile.ZipFile(archive) as bundle:
        sources = {name: hashlib.sha256(bundle.read(name)).hexdigest() for name in
                   ('scripts/nas_capacity_agent.py', 'scripts/nas_vm_file_capacity.py')}
    assert sources == {name: vm.digest(ROOT / name) for name in sources}
    return {'native_linux_validation_sha256': vm.digest(folder / 'linux-validation.json'),
            'qualified_sources_sha256': sources, 'original_workload_acceptance_proven': False}


def engine_memory_binding():
    folder = BASE / 'engine-memory-20261015'
    proof = read(folder / 'deployment-proof.json')
    tests = read(folder / 'linux-worker-validation.json')
    assert proof['engine_memory_low_bytes'] == 1536 * 1024**2
    assert all(proof[k] is True for k in (
        'hard_limits_mounts_images_inner_ids_and_configs_unchanged',
        'controller_postgres_not_restarted', 'global_parent_settings_unchanged',
        'recursive_protection_mount_verified'))
    assert proof['production_modified'] is False and proof['lease_and_http_timeouts_changed'] is False
    assert tests['engine_container_id'] == proof['engine_container_id']
    assert tests['all_passed'] is True and tests['linux_worker_tests'] == 28
    assert tests['original_workload_acceptance_proven'] is False
    return {'deployment_sha256': vm.digest(folder / 'deployment-proof.json'),
            'linux_validation_sha256': vm.digest(folder / 'linux-worker-validation.json'),
            'engine_container_id': proof['engine_container_id'], 'original_workload_acceptance_proven': False}


def original_workload_binding(diagnostic_reference=None, *, attempt=None):
    from nas_original_workload import binding

    attempt = ATTEMPT if attempt is None else attempt
    if attempt in {'v', 'w', 'x', 'y'}:
        return binding(vm.DISK_QOS_FILE_MEMORY_PROFILE, upstream_transport=True, guest_dns=True, resident=True, resident_attempt=attempt)
    if attempt in {'t', 'u', 'v', 'w', 'x', 'y'}:
        return binding(vm.DISK_QOS_FILE_MEMORY_PROFILE, upstream_transport=True, guest_dns=True)
    if attempt in {'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'}:
        return binding(vm.DISK_QOS_FILE_MEMORY_PROFILE, upstream_transport=True)
    diagnostic = DIAGNOSTIC_REFERENCE if diagnostic_reference is None else diagnostic_reference
    return (binding(vm.DISK_QOS_FILE_MEMORY_PROFILE, diagnostic_reference=True) if diagnostic else
            binding(vm.DISK_QOS_FILE_MEMORY_PROFILE))


def failed_original_reference_binding(attempt=None):
    attempt = ATTEMPT if attempt is None else attempt
    if attempt == 'y':
        from nas_failed_w_reference import binding

        return binding()
    from nas_original_workload import PHYSICAL_SOURCES, validate_failed_reference

    case = BASE / 'day-p-rust-leroy-20261015'
    window = BASE / 'resource-window-day-20261015-p-rust-leroy'
    paths = {'run': case / 'leroy-run.json', 'window': window / 'window-result.json',
             'archive': window / 'closed-disk-archive.json', 'restored': window / 'restored-window.json',
             'production': window / 'production-boundary-resolution.json',
             'plan': BASE / 'day-window-plan-20261015-p-rust-leroy/approval.json',
             'memory': case / 'leroy-memory-summary.json', 'target': case / 'leroy-target-before.json',
             'receipt': case / 'offline-quality-leroy/result.json'}
    value = validate_failed_reference({key: read(path) for key, path in paths.items()},
                                     {name: vm.digest(ROOT / name) for name in PHYSICAL_SOURCES})
    value['source_evidence_sha256'] = {p.relative_to(BASE).as_posix(): vm.digest(p) for p in paths.values()}
    return value


def ssh_transport_binding(attempt='k'):
    assert attempt in {'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'}
    if attempt in {'v', 'w', 'x', 'y'}:
        folder = BASE / ('original-workload-resident-qualification-20261017' + ('-' + attempt if attempt in {'w', 'x', 'y'} else ''))
        proof = read(folder / 'linux-validation.json')
        assert proof['all_passed'] and proof['native_linux_tests'] >= 100 and proof['failures_or_skips'] == 0
        assert proof['original_ci_dispatched'] is False and proof['guest_ssh_requests'] is False
        assert vm.digest(folder / 'inputs.zip') == proof['inputs_sha256']
        with zipfile.ZipFile(folder / 'inputs.zip') as bundle:
            for name in ('scripts/nas_release_vm.py', 'tests/test_nas_ssh_transport.py'):
                assert hashlib.sha256(bundle.read(name)).hexdigest() == vm.digest(ROOT / name)
        return {'linux_validation_sha256': vm.digest(folder / 'linux-validation.json'),
                'source_sha256': vm.digest(ROOT / 'scripts/nas_release_vm.py'), 'additional_sources_sha256': {},
                'operation_results_still_unknown_after_transport_loss': True}
    folder = BASE / ('ssh-transport-20261015-c' if attempt in {'m', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'} else
                     'ssh-transport-20261015-b' if attempt == 'l' else 'ssh-transport-20261015')
    proof = read(folder / 'linux-validation.json')
    assert proof['all_passed'] is True and proof['linux_tests'] == (15 if attempt == 'k' else 23)
    assert proof['failures_or_skips'] == 0 and proof['real_ssh_requests_sent'] is False
    assert proof['production_modified'] is False and proof['image_rebuilt'] is False
    archive = folder / 'inputs.zip'
    assert vm.digest(archive) == proof['inputs_sha256']
    with zipfile.ZipFile(archive) as bundle:
        source_sha = hashlib.sha256(bundle.read('scripts/nas_release_vm.py')).hexdigest()
        assert source_sha == vm.digest(ROOT / 'scripts/nas_release_vm.py')
        assert hashlib.sha256(bundle.read('tests/test_nas_ssh_transport.py')).hexdigest() == vm.digest(ROOT / 'tests/test_nas_ssh_transport.py')
        additional = {}
        if attempt in {'l', 'm'}:
            for name in ('scripts/nas_followup_support.py', 'scripts/nas_vm_file_capacity.py', 'tests/test_nas_admission_reads.py'):
                additional[name] = hashlib.sha256(bundle.read(name)).hexdigest()
                assert additional[name] == vm.digest(ROOT / name)
    return {'linux_validation_sha256': vm.digest(folder / 'linux-validation.json'),
            'source_sha256': source_sha, 'additional_sources_sha256': additional,
            'operation_results_still_unknown_after_transport_loss': True}


def control_working_set_binding():
    folder = BASE / 'control-working-set-20261015'
    path = folder / 'deployment-proof.json'
    proof = read(path)
    assert proof['controller_reservation_after_bytes'] == 256 * 1024**2
    assert proof['own_parent_memory_low_after_bytes'] == 448 * 1024**2
    assert proof['controller_hard_limit_bytes'] == 512 * 1024**2
    assert proof['images_service_ids_pids_mounts_and_other_resources_unchanged'] is True
    assert proof['global_parent_settings_unchanged'] is True
    assert proof['ci_lease_deadlines_changed'] is False and proof['production_modified'] is False
    assert proof['original_sources_tests_or_fixture_limits_changed'] is False
    assert proof['workload_acceptance_proven'] is False
    health = folder / 'idle-health-validation.json'
    assert read(health)['all_http200'] is True
    return {'deployment_sha256': vm.digest(path), 'idle_health_sha256': vm.digest(health),
            'heavy_workload_acceptance_proven': False}


def interrupted_reference(phase, attempt):
    if phase != 'rust-jenkins' or attempt not in {'g', 'h'}:
        return False
    path = BASE / 'day-g-rust-leroy-20261015/leroy-run.json'
    return read(path)['status'] == 'interrupted'


def interrupted_reference_binding():
    """Permit a diagnostic Jenkins reference without accepting the failed Leroy run."""
    from nas_vm_capacity_reference import PHYSICAL_SOURCES

    case = BASE / 'day-g-rust-leroy-20261015'
    window = BASE / 'resource-window-day-20261015-g-rust-leroy'
    run = read(case / 'leroy-run.json')
    assert run['status'] == 'interrupted' and run['reason'] == 'Runner lease expired; external effects require reconciliation'
    assert not run['cancel_requested'] and run['commit'] == vm.COMMIT
    assert run['parameters']['CHECK_GROUP'] == 'server-test'
    assert run['snapshot']['source']['application_patches_applied'] is False
    result = read(window / 'window-result.json')
    assert result['original_rust_qualified'] is False
    assert all(result[key] is True for key in ('all_seven_original_services_restored_healthy',
               'healthy_before_deadline', 'native_jenkins_quiet', 'infrastructure_unchanged',
               'controller_process_unchanged', 'controller_no_new_oom'))
    assert read(window / 'closed-disk-archive.json')['source_removed'] is True
    assert not read(window / 'restored-window.json').get('host_reserve_stop')
    plan = read(BASE / 'day-window-plan-20261015-g-rust-leroy/approval.json')
    assert plan['resource_profile'] == vm.DISK_QOS_FILE_MEMORY_PROFILE
    sources = {name: vm.digest(ROOT / name) for name in PHYSICAL_SOURCES}
    assert all(plan['script_sha256'][name] == sha for name, sha in sources.items())
    summary = read(case / 'leroy-memory-summary.json')
    assert summary['aligned_guest_host_samples'] > 0
    assert summary['minimum_host_available_kib'] >= vm.MIN_HOST_AVAILABLE_MB * 1024
    assert summary['minimum_host_swap_free_kib'] >= vm.MIN_HOST_SWAP_MB * 1024
    target = read(case / 'leroy-target-before.json')
    assert target['manifest']['commit'] == vm.COMMIT
    assert target['manifest']['runtimeImageId'] == 'sha256:6251c60f499e41e706613f931bf281ce52312b957d5a6a123cf4e27dd3242585'
    assert target['manifest']['files']['verification-source.tar.gz'] == 'f0c737a8133cd73f6b34c66be5081316a7047a1881583532874b40abaec59708'
    assert len(target['containers']) == 4 and all(row['health'] == 'healthy' for row in target['containers'])
    capacity = read(case / 'leroy-file-memory-capacity.json')
    assert capacity['qualified_synthetic_capacity'] and capacity['all_page_markers_intact']
    assert capacity['allocated_mib'] == 5888 and capacity['hold_seconds'] >= 60
    files = {name: vm.digest(case / name) for name in ('leroy-run.json', 'leroy-target-before.json',
             'leroy-file-memory-capacity.json', 'leroy-memory-summary.json')}
    return {'diagnostic_reference_only': True, 'interrupted_leroy_run_id': run['id'],
            'source_evidence_sha256': files, 'physical_sources_sha256': sources,
            'full_release_still_requires_both_successful_original_rust_runs': True,
            'equal_background_load_proven': False, 'production_ready': False}


def failed_observer_reference_binding():
    """A new reference may follow G's observer failure, never reuse its CI result."""
    from nas_vm_capacity_reference import PHYSICAL_SOURCES

    case = BASE / 'day-g-rust-jenkins-20261015'
    window = BASE / 'resource-window-day-20261015-g-rust-jenkins'
    result = read(window / 'window-result.json')
    assert result['outcome'] == 'stopped:original_jenkins_status_ssh_timeout'
    assert result['original_rust_qualified'] is False and result['diagnostic_reference_only'] is True
    assert all(result[key] is True for key in (
        'all_seven_original_services_restored_healthy', 'healthy_before_deadline', 'native_jenkins_quiet',
        'infrastructure_unchanged', 'controller_process_unchanged', 'controller_no_new_oom'))
    assert read(window / 'closed-disk-archive.json')['source_removed'] is True
    assert not read(window / 'restored-window.json').get('host_reserve_stop')
    assert read(window / 'stage-result.json')['exit_code'] == 1
    collected = read(case / 'aborted-original-ci-collection.json')
    assert collected['original_ci_terminal'] is True and collected['original_ci_restarted'] is False
    assert collected['new_pipeline_dispatched'] is False and collected['test_completion_claimed'] is False
    assert collected['operator_stop_to_finish_observer_failure_cleanup'] is True
    job = read(case / 'jenkins-build.json')
    assert job['number'] == collected['number'] == 28 and not job['building'] and job['result'] == 'ABORTED'
    assert vm.COMMIT in job['checkout_revisions']
    plan = read(BASE / 'day-window-plan-20261015-g-rust-jenkins/approval.json')
    assert plan['source_commit'] == vm.COMMIT and plan['resource_profile'] == vm.DISK_QOS_FILE_MEMORY_PROFILE
    sources = {name: vm.digest(ROOT / name) for name in PHYSICAL_SOURCES}
    assert all(plan['script_sha256'][name] == sha for name, sha in sources.items()), 'Reference VM configuration changed'
    paths = (window / 'window-result.json', window / 'stage-result.json', window / 'closed-disk-archive.json',
             case / 'aborted-original-ci-collection.json', case / 'jenkins-build.json')
    return {'reference_case': case.name, 'original_job': 28, 'original_result': 'ABORTED',
            'source_evidence_sha256': {path.relative_to(BASE).as_posix(): vm.digest(path) for path in paths},
            'physical_sources_sha256': sources, 'original_ci_results_reused': False,
            'diagnostic_reference_only': True, 'production_ready': False}


def validate_approval(value):
    phase = value['phase']
    attempt = value.get('attempt', 'a')
    assert attempt in ATTEMPTS
    assert phase in PHASES and value['user_approved'] is True
    assert attempt != 'x' or phase.startswith('release-')
    assert attempt != 'y' or (phase == 'rust-jenkins' and value.get('diagnostic_reference_only') is True)
    from nas_open_authorization import REQUEST

    assert value['explicit_user_request'] == (REQUEST if attempt in {'v', 'w', 'x', 'y'} else CONTINUATION_REQUEST if attempt in {'m', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u'} else 'den ganzen Tag')
    assert value['window'] == window_name(phase, attempt) and value['engine'] == phase.rsplit('-', 1)[1]
    assert value['comparison_rounds'] == [round_name(phase, attempt)] and value['source_commit'] == vm.COMMIT
    assert value['maximum_window_seconds'] == maximum_window_seconds(attempt) and value['resource_profile'] == resource_profile(attempt)
    order = value.get('guest_page_reporting_order', 0)
    assert type(order) is int and order == page_reporting_order(attempt)
    assert value['day_end_epoch'] == authorization_end(attempt)
    end = authorization_end(attempt)
    maximum = value['created_at_epoch'] + maximum_window_seconds(attempt)
    assert time.time() < value['absolute_deadline_epoch'] <= (maximum if end is None else min(end, maximum))
    assert value['services'] == list(SERVICES) and value['production_cutover'] is False
    assert value['application_sources_tests_and_fixture_limits_unchanged'] is True
    if attempt == 'x':
        from nas_rust_reference import binding as rust_binding

        assert value['rust_reference_binding'] == rust_binding()
    assert value['script_sha256'] == {name: vm.digest(ROOT / name) for name in SOURCES}
    if attempt in {'w', 'x', 'y'}:
        from nas_console_binding import binding

        assert value['console_logging_binding'] == binding()
    if attempt in MATCHED_ATTEMPTS or phase.startswith('release-'):
        from nas_ci_background import capacity_proof

        assert value['matching_ci_background'] is True and value['ci_slots'] == 2
        assert value['ci_capacity_alignment_proof_sha256'] == capacity_proof()
    if attempt == 'f':
        from nas_vm_capacity_reference import binding

        assert value['separate_capacity_reference'] == binding(resource_profile(attempt))
    if attempt in {'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'}:
        assert value['control_working_set_binding'] == control_working_set_binding()
    if attempt in {'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'}:
        assert value['engine_memory_binding'] == engine_memory_binding()
    if attempt == 'k':
        assert value['ssh_transport_binding'] == ssh_transport_binding()
    if attempt == 'l':
        assert value['ssh_transport_binding'] == ssh_transport_binding('l')
    if attempt in {'m', 'n', 'o'}:
        assert value['ssh_transport_binding'] == ssh_transport_binding(attempt)
        assert value['nas_local_capacity'] is True and value['local_capacity_binding'] == local_capacity_binding(attempt)
        assert value['continuation_authorization'] == (open_authorization_binding(attempt) if attempt in {'v', 'w', 'x', 'y'} else continuation_binding())
    if attempt in {'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'}:
        assert value['original_workload_qualification'] is True
        assert not value.get('nas_local_capacity') and not value.get('separate_capacity_reference')
        if value.get('diagnostic_reference_only'):
            assert attempt in {'p', 'y'} and phase == 'rust-jenkins'
            assert value['failed_original_leroy_reference'] == failed_original_reference_binding(attempt)
            assert value['original_workload_binding'] == original_workload_binding(True, attempt=attempt)
        else:
            expected = (original_workload_binding(attempt=attempt) if attempt in {'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'} else original_workload_binding())
            assert value['original_workload_binding'] == expected
        assert value['continuation_authorization'] == (open_authorization_binding(attempt) if attempt in {'v', 'w', 'x', 'y'} else continuation_binding())
        assert value['ssh_transport_binding'] == ssh_transport_binding(attempt)
        if attempt in {'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'}:
            from nas_graphato_transport import binding

            assert value['graphato_transport_binding'] == binding()
        if attempt in {'t', 'u', 'v', 'w', 'x', 'y'}:
            from nas_vm_dns import POLICY, reference_binding

            assert value['guest_dns_policy'] == POLICY
            assert value['dns_failure_reference'] == reference_binding()
    if interrupted_reference(phase, attempt):
        assert value['interrupted_leroy_reference'] == interrupted_reference_binding()
        if attempt == 'h':
            assert value['failed_observer_reference'] == failed_observer_reference_binding()


def prepare(phase):
    assert not DIAGNOSTIC_REFERENCE or (ATTEMPT in {'p', 'y'} and phase == 'rust-jenkins')
    plan = BASE / ('day-window-plan-20261015-' + ('' if ATTEMPT == 'a' else ATTEMPT + '-') + phase)
    assert not plan.exists(), 'Do not replace an earlier plan or reopen a window'
    now = time.time()
    end = authorization_end(ATTEMPT)
    maximum = maximum_window_seconds(ATTEMPT)
    deadline = now + maximum - 120 if end is None else min(end, now + maximum - 120)
    assert deadline - now >= 8100, 'Keep at least two hours for original CI plus recovery'
    value = {'user_approved': True, 'explicit_user_request': CONTINUATION_REQUEST if ATTEMPT in {'m', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'} else 'den ganzen Tag',
             'question_context': 'Bis zu welcher Uhrzeit morgen früh dürfen die sieben NAS-Dienste für die weiteren Prüfungen pausiert sein?',
             'created_at_epoch': now, 'phase': phase, 'attempt': ATTEMPT, 'window': window_name(phase),
             'engine': phase.rsplit('-', 1)[1], 'maximum_window_seconds': maximum,
             'absolute_deadline_epoch': deadline, 'day_end_epoch': authorization_end(ATTEMPT), 'restore_margin_seconds': 900,
             'services': list(SERVICES), 'comparison_rounds': [round_name(phase)], 'source_commit': vm.COMMIT,
             'resource_profile': resource_profile(ATTEMPT), 'application_sources_tests_and_fixture_limits_unchanged': True,
             'guest_page_reporting_order': page_reporting_order(ATTEMPT),
             'host_swap_and_kernel_settings_changed': False, 'production_cutover': False,
             'script_sha256': {name: vm.digest(ROOT / name) for name in SOURCES}}
    if ATTEMPT in {'v', 'w', 'x', 'y'}:
        from nas_open_authorization import REQUEST

        value['explicit_user_request'] = REQUEST
    if ATTEMPT in {'w', 'x', 'y'}:
        from nas_console_binding import binding

        value['console_logging_binding'] = binding()
    if ATTEMPT in MATCHED_ATTEMPTS or phase.startswith('release-'):
        from nas_ci_background import capacity_proof

        value.update(matching_ci_background=True, ci_slots=2, ci_capacity_alignment_proof_sha256=capacity_proof())
    if ATTEMPT == 'f':
        from nas_vm_capacity_reference import binding

        value['separate_capacity_reference'] = binding(resource_profile(ATTEMPT))
    if ATTEMPT in {'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'}:
        value['control_working_set_binding'] = control_working_set_binding()
    if ATTEMPT in {'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'}:
        value['engine_memory_binding'] = engine_memory_binding()
    if ATTEMPT == 'k':
        value['ssh_transport_binding'] = ssh_transport_binding()
    if ATTEMPT == 'l':
        value['ssh_transport_binding'] = ssh_transport_binding('l')
    if ATTEMPT in {'m', 'n', 'o'}:
        value.update(ssh_transport_binding=ssh_transport_binding(ATTEMPT), nas_local_capacity=True,
                     local_capacity_binding=local_capacity_binding(ATTEMPT), continuation_authorization=continuation_binding())
    if ATTEMPT in {'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'}:
        value.update(original_workload_qualification=True, original_workload_binding=original_workload_binding(),
                     continuation_authorization=open_authorization_binding() if ATTEMPT in {'v', 'w', 'x', 'y'} else continuation_binding(), ssh_transport_binding=ssh_transport_binding(ATTEMPT))
        if ATTEMPT in {'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'}:
            from nas_graphato_transport import binding

            value['graphato_transport_binding'] = binding()
        if ATTEMPT in {'t', 'u', 'v', 'w', 'x', 'y'}:
            from nas_vm_dns import POLICY, reference_binding

            value.update(guest_dns_policy=POLICY, dns_failure_reference=reference_binding())
        if DIAGNOSTIC_REFERENCE:
            value.update(diagnostic_reference_only=True, failed_original_leroy_reference=failed_original_reference_binding())
    if interrupted_reference(phase, ATTEMPT):
        value['interrupted_leroy_reference'] = interrupted_reference_binding()
        if ATTEMPT == 'h':
            value['failed_observer_reference'] = failed_observer_reference_binding()
    if ATTEMPT == 'x':
        from nas_rust_reference import binding as rust_binding

        value['rust_reference_binding'] = rust_binding()
    validate_approval(value)
    from nas_resource_window_guard import window_policy

    assert window_policy(value, value['window']) == (maximum, value['comparison_rounds'], 900)
    plan.mkdir()
    write(plan / 'approval.json', value)
    for name in value['script_sha256']:
        dest = plan / 'approved-sources' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, dest)
    print(json.dumps({'plan': str(plan.relative_to(ROOT)), 'deadline_epoch': deadline, 'nas_actions': False}), flush=True)


def prerequisites(phase):
    assert not DIAGNOSTIC_REFERENCE or (ATTEMPT in {'p', 'y'} and phase == 'rust-jenkins'), 'Diagnostic reference cannot waive release prerequisites'
    assert read(BASE / 'resource-window-original-night-20261014-f/window-result.json')['all_seven_original_services_restored_healthy']
    if ATTEMPT == 'y':
        assert DIAGNOSTIC_REFERENCE and phase == 'rust-jenkins'
        failed_original_reference_binding()
    elif ATTEMPT == 'x':
        from nas_console_binding import binding
        from nas_rust_reference import binding as rust_binding

        assert phase.startswith('release-')
        rust_binding(verify_evidence=True)
        binding(current=True)
    elif ATTEMPT == 'w':
        previous = BASE / 'resource-window-acceptance-20261017-v-rust-leroy'
        result = read(previous / 'window-result.json')
        assert result['original_rust_qualified'] is False
        assert all(result[k] is True for k in ('all_seven_original_services_restored_healthy',
                   'healthy_before_deadline', 'native_jenkins_quiet', 'infrastructure_unchanged'))
        archive = read(previous / 'closed-disk-archive.json')
        assert archive['source_removed'] and archive['copy_sha256'] == archive['sha256']
        from nas_console_binding import binding

        binding(current=True)
    elif ATTEMPT == 'v':
        audit = read(BASE / 'status-20261017-u/summary.json')
        assert audit['status'] == 'interrupted' and not audit['original_rust_qualified']
        assert audit['window_phase'] == 'restored' and audit['current_seven_healthy_stable']
        assert audit['vm_running'] is False and audit['native_jenkins_jobs_same_as_before_window']
        archive = read(BASE / 'resource-window-day-20261015-u-rust-leroy/closed-disk-archive.json')
        assert archive['source_removed'] and archive['copy_sha256'] == archive['sha256']
    elif ATTEMPT in MATCHED_ATTEMPTS:
        previous = BASE / ('resource-window-day-20261015-rust-jenkins' if ATTEMPT == 'b' else
                           'resource-window-day-20261015-b-rust-leroy' if ATTEMPT == 'c' else
                           'resource-window-day-20261015-c-rust-leroy' if ATTEMPT == 'd' else
                           'resource-window-day-20261015-d-rust-leroy' if ATTEMPT == 'e' else
                           'resource-window-day-20261015-e-rust-leroy' if ATTEMPT == 'f' else
                           'resource-window-day-20261015-f-rust-leroy' if ATTEMPT == 'g' else
                           'resource-window-day-20261015-g-rust-jenkins' if ATTEMPT == 'h' else
                           'resource-window-day-20261015-h-rust-jenkins' if ATTEMPT == 'i' else
                           'resource-window-day-20261015-i-rust-leroy' if ATTEMPT == 'j' else
                           'resource-window-day-20261015-j-rust-leroy' if ATTEMPT == 'k' else
                           'resource-window-day-20261015-k-rust-leroy' if ATTEMPT == 'l' else
                           'resource-window-day-20261015-l-rust-leroy' if ATTEMPT == 'm' else
                           'resource-window-day-20261015-m-rust-leroy' if ATTEMPT == 'n' else
                           'resource-window-day-20261015-n-rust-leroy' if ATTEMPT == 'o' else
                           'resource-window-day-20261015-o-rust-leroy' if ATTEMPT == 'p' else
                           'resource-window-day-20261015-p-rust-jenkins' if ATTEMPT in {'q', 'r', 's'} else
                           'resource-window-day-20261015-s-rust-leroy' if ATTEMPT == 't' else
                           'resource-window-day-20261015-t-rust-leroy')
        assert read(previous / 'window-result.json')['all_seven_original_services_restored_healthy']
        assert read(previous / 'closed-disk-archive.json')['source_removed']
        from nas_ci_background import capacity_proof

        capacity_proof()
    reference = interrupted_reference(phase, ATTEMPT) or DIAGNOSTIC_REFERENCE
    if phase != 'rust-leroy' and not reference and not (ATTEMPT == 'x' and phase == 'release-leroy'):
        earlier = PHASES[PHASES.index(phase) - 1]
        assert read(BASE / window_name(earlier) / 'window-result.json')['all_seven_original_services_restored_healthy']
    if reference:
        if DIAGNOSTIC_REFERENCE:
            failed_original_reference_binding()
        else:
            interrupted_reference_binding()
            if ATTEMPT == 'h':
                failed_observer_reference_binding()
    elif phase != 'rust-leroy':
        require_day_rust('leroy')
    if phase.startswith('release-'):
        require_day_rust('jenkins')


def require_day_rust(engine):
    if ATTEMPT == 'x':
        from nas_rust_reference import evidence

        return evidence(engine)
    case = BASE / round_name('rust-' + engine)
    evidence = require_rust_evidence(case, engine)
    if ATTEMPT in MATCHED_ATTEMPTS:
        window = BASE / window_name('rust-' + engine)
        result = read(window / 'window-result.json')
        assert not result.get('diagnostic_reference_only'), 'Diagnostic reference cannot qualify full release'
        assert all(result[key] is True for key in (
            'original_rust_qualified', 'all_seven_original_services_restored_healthy',
            'native_jenkins_quiet', 'infrastructure_unchanged', 'controller_process_unchanged',
            'controller_no_new_oom'))
        assert read(window / 'closed-disk-archive.json')['source_removed'] is True
        assert not read(window / 'restored-window.json').get('host_reserve_stop')
        prepared = read(case / 'prepared.json')
        assert prepared['resource_profile'] == resource_profile(ATTEMPT)
        assert prepared['matching_ci_background'] is True and prepared['ci_slots'] == 2
        if ATTEMPT in {'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'}:
            reporting = read(case / (engine + '-guest-page-reporting.json'))
            assert reporting['configured_order'] == page_reporting_order(ATTEMPT)
            assert reporting['minimum_reported_block_bytes'] == 65536
        if ATTEMPT in {'m', 'n', 'o'}:
            capacity = read(case / (engine + '-file-memory-capacity.json'))
            assert capacity['nas_local_admission'] is True and prepared['nas_local_capacity'] is True
            if ATTEMPT == 'o':
                keepalive = capacity['active_probe_keepalive']
                assert keepalive['stopped'] is True and keepalive['existing_mux_only'] is True
                assert keepalive['counts_as_hold_or_marker_check'] is False
                assert keepalive['idle_and_hard_timeout_limits_changed'] is False
        if ATTEMPT in {'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'}:
            from nas_original_workload import verify_retained

            assert prepared['original_workload_qualification'] is True and prepared['synthetic_capacity_qualified'] is False
            verify_retained(case, engine)
            if ATTEMPT in {'t', 'u', 'v', 'w', 'x', 'y'}:
                from nas_vm_dns import POLICY, UPSTREAMS

                assert read(case / (engine + '-guest-dns.json'))['policy'] == POLICY
                assert read(case / (engine + '-target-after.json'))['test_environment_dns']['upstreams'] == list(UPSTREAMS)
        if ATTEMPT == 'f':
            from nas_vm_capacity_reference import binding

            assert prepared['separate_capacity_reference'] == binding(resource_profile(ATTEMPT))
        from nas_ci_background import capacity_proof

        before = read(case / (engine + '-ci-background-before.json'))
        assert before == read(case / (engine + '-ci-background-after.json'))
        assert before['capacity_alignment_proof_sha256'] == capacity_proof()
    return evidence


def restore_until_finished(remote, *, folder=None, deadline_epoch=None):
    budget = 900 if deadline_epoch is None else min(900, max(0, deadline_epoch - time.time()))
    until = time.monotonic() + budget
    while True:
        remaining = until - time.monotonic()
        if remaining <= 21:
            raise RuntimeError('Recovery remains incomplete; inspect the independent NAS watchdog')
        try:
            state = action(remote, 'restore', operation_timeout=min(400, int(remaining) - 20))
        except (subprocess.TimeoutExpired, OSError) as error:
            # The first request may already have restored services. The same
            # journal's restore action is idempotent; never pause or reopen it.
            if folder is not None:
                row = {'at_epoch': time.time(), 'action': 'restore', 'error_type': type(error).__name__,
                       'outcome_unknown': True, 'original_ci_restarted': False}
                with (folder / 'recovery-observation-errors.jsonl').open('a') as stream:
                    stream.write(json.dumps(row) + '\n')
        else:
            if state['phase'] == 'restored':
                return state
            assert state['phase'] == 'restore_error', 'Unexpected recovery state; independent NAS watchdog remains active'
        if time.monotonic() >= until - 21:
            raise RuntimeError('Recovery remains incomplete; inspect the independent NAS watchdog')
        time.sleep(min(15, max(0, until - time.monotonic() - 21)))


def observe_original_stage(process, approval, remote, case, folder):
    """Keep the existing stage through an uncertain registration response."""
    while process.poll() is None:
        validate_approval(approval)
        assert time.time() < approval['absolute_deadline_epoch'] - 900, 'Preserve the fixed recovery margin'
        try:
            register_runs(remote, case)
            state = action(remote, 'register-vm')
        except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as error:
            row = {'at_epoch': time.time(), 'error_type': type(error).__name__,
                   'outcome_unknown': True, 'original_ci_restarted': False}
            with (folder / 'stage-observation-errors.jsonl').open('a') as stream:
                stream.write(json.dumps(row) + '\n')
        else:
            (folder / 'latest-window-state.json').write_text(json.dumps(state, indent=2) + '\n')
            assert state['deadline'] == approval['absolute_deadline_epoch']
            assert state['phase'] == 'paused' and time.time() < state['deadline'] - 900
        remaining = approval['absolute_deadline_epoch'] - 900 - time.time()
        assert remaining > 0, 'Preserve the fixed recovery margin'
        time.sleep(min(15, remaining))


def run(phase):
    approval = read(BASE / ('day-window-plan-20261015-' + ('' if ATTEMPT == 'a' else ATTEMPT + '-') + phase) / 'approval.json')
    validate_approval(approval)
    assert approval.get('diagnostic_reference_only', False) == DIAGNOSTIC_REFERENCE
    prerequisites(phase)
    folder = BASE / window_name(phase)
    assert not folder.exists(), 'Observe the retained stage; never redispatch it'
    folder.mkdir()
    remote = '/volume1/docker/leroy-nas-parity/' + folder.name
    prepare_on_nas(folder, remote, approved_day_plan=approval)
    if ATTEMPT in {'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'}:
        resources = read(folder / 'infrastructure-before.json')['services']['controller']['resources']
        assert resources['MemoryReservation'] == 256 * 1024**2
        assert resources['Memory'] == resources['MemorySwap'] == 512 * 1024**2
    if ATTEMPT in {'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'}:
        engine = read(folder / 'infrastructure-before.json')['services']['docker']
        binding = approval['engine_memory_binding']
        assert engine['resources']['CgroupParent'] == '-.slice'
        assert engine['resources']['MemoryReservation'] == 1536 * 1024**2
        program = 'EXPECTED=' + repr(binding['engine_container_id']) + '\n' + r'''
import json,pathlib,subprocess
c=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-docker-1'],text=True,timeout=20))[0]
assert c['Id']==EXPECTED and c['State']['Running'] and c['State']['Health']['Status']=='healthy'
scope=pathlib.Path('/sys/fs/cgroup')/('docker-'+EXPECTED+'.scope')
assert (scope/'memory.low').read_text().strip()==str(1536*1024**2)
assert (scope/'memory.min').read_text().strip()=='0'
print('verified')
'''
        assert vm.remote(program, sudo=True, timeout=30).strip() == 'verified'
    process = None
    outcome = 'not_dispatched'
    qualified = False
    engine = approval['engine']
    case = BASE / round_name(phase)
    try:
        write(folder / 'paused.json', action(remote, 'pause'))
        args = [str(ROOT / ('scripts/diagnose_nas_release_group.py' if phase.startswith('rust-') else 'scripts/compare_nas_full_release.py')),
                '--folder', case.relative_to(ROOT).as_posix(), '--engine', engine,
                '--resource-profile', approval['resource_profile'], '--postgres-init', '--memory-trace',
                '--page-reporting-order', str(page_reporting_order(ATTEMPT)), '--early-memory-pressure']
        args += ['--group', 'server-test'] if phase.startswith('rust-') else ['--first-engine', 'leroy']
        if approval.get('nas_local_capacity'):
            args += ['--nas-local-capacity']
        if approval.get('original_workload_qualification'):
            args += ['--original-workload-qualification']
        if approval.get('separate_capacity_reference'):
            args += ['--separate-capacity-reference']
        if approval.get('matching_ci_background'):
            args += ['--matching-ci-background']
        idle()
        with (folder / 'stage-stdout.log').open('xb') as out, (folder / 'stage-stderr.log').open('xb') as err:
            process = subprocess.Popen([sys.executable, *args], cwd=ROOT, stdout=out, stderr=err)
            write(folder / 'stage-started.json', {'pid': process.pid, 'at_epoch': time.time(), 'ci_redispatched': False})
            observe_original_stage(process, approval, remote, case, folder)
            write(folder / 'stage-result.json', {'exit_code': process.returncode, 'at_epoch': time.time()})
        assert process.returncode == 0, 'Retain the original stage and investigate its collection failure'
        if phase.startswith('rust-'):
            evidence = require_rust_evidence(case, engine)
            write(folder / 'rust-qualification.json', evidence)
            qualified = True
        outcome = 'original_stage_collected'
        idle()
        vm.stop()
        stop_private_jenkins()
        if approval['resource_profile'] in vm.FILE_MEMORY_PROFILES:
            from nas_vm_file_memory import release_memory_file

            release_memory_file(case, engine)
        from archive_nas_day_disk import archive

        archive(folder, approval, engine)
    except Exception as error:
        outcome = 'stopped:' + type(error).__name__
        write(folder / 'operation-error.json', {'type': type(error).__name__, 'original_ci_restarted': False})
        raise
    finally:
        state = restore_until_finished(remote, folder=folder, deadline_epoch=approval['absolute_deadline_epoch'])
        write(folder / 'restored-window.json', state)
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=20)
        recovery = verify_recovery(folder, remote)
        after = infrastructure()
        write(folder / 'infrastructure-after.json', after)
        before = read(folder / 'infrastructure-before.json')
        production = production_jobs()
        write(folder / 'production-after.json', production)
        result = {'at': datetime.now(timezone.utc).isoformat(), 'phase': phase, 'outcome': outcome,
                  'original_rust_qualified': qualified, 'all_seven_original_services_restored_healthy': True,
                  'healthy_before_deadline': recovery['at_epoch'] < state['deadline'],
                  'native_jenkins_quiet': not production['active_builds'] and production['jobs'] == read(folder / 'production-before.json')['jobs'],
                  'infrastructure_unchanged': all(before[k] == after[k] for k in ('services', 'configuration_sha256', 'postgres_durability', 'comparison_driver_sha256')),
                  'controller_process_unchanged': before['states']['controller'] == after['states']['controller'],
                  'controller_no_new_oom': all(before['controller_memory']['memory.events'][k] == after['controller_memory']['memory.events'][k] for k in ('oom', 'oom_kill')),
                  'production_cutover': False, 'production_ready': False}
        if approval.get('interrupted_leroy_reference') or approval.get('diagnostic_reference_only'):
            result['diagnostic_reference_only'] = True
        write(folder / 'window-result.json', result)
        print(json.dumps(result), flush=True)


def main():
    global DIAGNOSTIC_REFERENCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', required=True, choices=PHASES)
    parser.add_argument('--attempt', choices=ATTEMPTS, default='a')
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--run-approved', action='store_true')
    parser.add_argument('--diagnostic-reference', action='store_true')
    args = parser.parse_args()
    assert args.prepare != args.run_approved
    configure_attempt(args.attempt)
    DIAGNOSTIC_REFERENCE = args.diagnostic_reference
    (prepare if args.prepare else run)(args.phase)


if __name__ == '__main__':
    main()
