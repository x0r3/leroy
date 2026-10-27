"""Real-job qualification must retain negative stress and all original-job gates."""
import copy
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_original_workload as original  # noqa: E402


@pytest.mark.parametrize('attempt', ['q', 'r', 's', 't', 'u'])
@pytest.mark.parametrize('phase', ['rust-leroy', 'rust-jenkins', 'release-leroy', 'release-jenkins'])
def test_new_namespace_is_recognized_by_the_actual_nas_recovery_policy(monkeypatch, attempt, phase):
    import nas_resource_window_guard as guard

    monkeypatch.setattr(guard.time, 'time', lambda: guard.CONTINUATION_END - 10000)
    case = ('day-' + attempt + '-' + phase + '-20261015' if phase.startswith('rust-')
            else 'day-' + attempt + '-release-20261015')
    plan = {'maximum_window_seconds': 14400, 'user_approved': True, 'source_commit': original.vm.COMMIT,
            'comparison_rounds': [case], 'absolute_deadline_epoch': guard.CONTINUATION_END,
            'explicit_user_request': 'Zwischenhinweis, dein Arbeitsfenster ist noch für den gesamten morgigen Tag freigegeben'}
    window = 'resource-window-day-20261015-' + attempt + '-' + phase
    assert guard.window_policy(plan, window) == (14400, [case], 900)
    with pytest.raises(AssertionError):
        guard.window_policy({**plan, 'absolute_deadline_epoch': guard.CONTINUATION_END + 1}, window)


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(original.vm, 'ROOT', tmp_path)
    monkeypatch.setattr(original, 'PHYSICAL_SOURCES', ('physical.py',))
    monkeypatch.setattr(original, 'QUALIFIED_SOURCES', ('physical.py',))
    (tmp_path / 'physical.py').write_text('same physical environment')
    base = tmp_path / 'test-results/nas-parity/followup'
    case = base / original.REFERENCE
    window = base / 'resource-window-day-20261015-o-rust-leroy'
    oldplan = base / 'day-window-plan-20261015-o-rust-leroy'
    for p in (case, window, oldplan):
        p.mkdir(parents=True)

    def write(path, value):
        path.write_text(json.dumps(value))

    write(window / 'window-result.json', {**dict.fromkeys(('all_seven_original_services_restored_healthy',
          'native_jenkins_quiet', 'infrastructure_unchanged', 'controller_process_unchanged', 'controller_no_new_oom'), True),
          'original_rust_qualified': False})
    write(window / 'closed-disk-archive.json', {'source_removed': True, 'copy_sha256': 'same', 'sha256': 'same'})
    write(window / 'restored-window.json', {})
    write(oldplan / 'approval.json', {'source_commit': original.vm.COMMIT,
          'resource_profile': original.vm.DISK_QOS_FILE_MEMORY_PROFILE,
          'script_sha256': {'physical.py': original.vm.digest(tmp_path / 'physical.py')}})
    (case / 'offline-capacity-forensics').mkdir()
    (case / 'offline-capacity-forensics/agent.jsonl').write_bytes(b'TimeoutError: timed out\n')
    write(case / 'nas-capacity-retained-evidence.json', {'negative': True})
    write(case / 'leroy-memory-summary.json', {'minimum_host_available_kib': 512 * 1024,
                                               'minimum_host_swap_free_kib': 4096 * 1024})
    qualification = base / 'original-workload-qualification-20261015'
    qualification.mkdir()
    with zipfile.ZipFile(qualification / 'inputs.zip', 'w') as archive:
        archive.write(tmp_path / 'physical.py', 'physical.py')
    write(qualification / 'linux-validation.json', {'all_passed': True, 'native_linux_tests': 19,
          'failures_or_skips': 0, 'vm_started': False, 'memory_load_started': False, 'guest_ssh_requests': False,
          'inputs_sha256': original.vm.digest(qualification / 'inputs.zip')})
    return base, case, window


def scope():
    return {'attempt': 'p', 'phase': 'rust-leroy', 'window': 'resource-window-day-20261015-p-rust-leroy',
            'comparison_rounds': ['day-p-rust-leroy-20261015'], 'engine': 'leroy', 'source_commit': original.vm.COMMIT,
            'resource_profile': original.vm.DISK_QOS_FILE_MEMORY_PROFILE, 'original_workload_qualification': True,
            'matching_ci_background': True, 'ci_slots': 2, 'application_sources_tests_and_fixture_limits_unchanged': True,
            'maximum_window_seconds': 14400, 'restore_margin_seconds': 900, 'production_cutover': False,
            'host_swap_and_kernel_settings_changed': False}


@pytest.mark.parametrize('change', [
    {'attempt': 'o'}, {'phase': 'release-jenkins'}, {'engine': 'jenkins'}, {'source_commit': 'changed'},
    {'comparison_rounds': ['other']}, {'original_workload_qualification': False}, {'nas_local_capacity': True},
    {'separate_capacity_reference': {'green': True}}, {'ci_slots': 1}, {'matching_ci_background': False},
    {'application_sources_tests_and_fixture_limits_unchanged': False}, {'maximum_window_seconds': 86400},
    {'restore_margin_seconds': 0}, {'production_cutover': True}, {'host_swap_and_kernel_settings_changed': True},
])
def test_original_job_mode_requires_its_own_exact_plan(change):
    original.validate_scope(scope(), 'day-p-rust-leroy-20261015', 'leroy')
    with pytest.raises(AssertionError):
        original.validate_scope({**scope(), **change}, 'day-p-rust-leroy-20261015', 'leroy')


def test_negative_stress_is_retained_without_claiming_capacity_or_ci_success(evidence):
    base, case, window = evidence
    value = original.binding(original.vm.DISK_QOS_FILE_MEMORY_PROFILE)
    assert value['synthetic_capacity_qualified'] is False and value['original_ci_results_reused'] is False
    assert value['complete_original_job_required'] and value['fresh_application_baseline_required']
    assert len(value['negative_evidence_sha256']) == 6
    (case / 'leroy-file-memory-capacity.json').write_text('{"qualified":true}')
    with pytest.raises(AssertionError):
        original.binding(original.vm.DISK_QOS_FILE_MEMORY_PROFILE)


def test_changed_physical_environment_invalidates_negative_reference(evidence):
    (original.vm.ROOT / 'physical.py').write_text('changed')
    with pytest.raises(AssertionError):
        original.binding(original.vm.DISK_QOS_FILE_MEMORY_PROFILE)


def test_missing_recovery_or_reserve_proof_is_not_a_workload_waiver(evidence):
    base, case, window = evidence
    path = window / 'window-result.json'
    value = json.loads(path.read_text())
    value['all_seven_original_services_restored_healthy'] = False
    path.write_text(json.dumps(value))
    with pytest.raises(AssertionError):
        original.binding(original.vm.DISK_QOS_FILE_MEMORY_PROFILE)


def test_retained_marker_is_not_an_original_ci_result_and_cannot_be_promoted(evidence, monkeypatch):
    base, case, window = evidence
    folder = base / 'day-p-rust-leroy-20261015'
    folder.mkdir()
    plan = base / 'day-window-plan-20261015-p-rust-leroy'
    plan.mkdir()
    value = {**scope(), 'script_sha256': {'physical.py': original.vm.digest(original.vm.ROOT / 'physical.py')},
             'original_workload_binding': original.binding(original.vm.DISK_QOS_FILE_MEMORY_PROFILE)}
    (plan / 'approval.json').write_text(json.dumps(value))
    monkeypatch.setitem(sys.modules, 'run_nas_day_window', SimpleNamespace(SOURCES=('physical.py',)))
    marker = original.expected_marker(folder, 'leroy')
    assert marker['synthetic_capacity_qualified'] is False and marker['original_ci_result_required'] is True
    path = folder / 'leroy-original-workload-qualification.json'
    path.write_text(json.dumps(marker))
    original.verify_retained(folder, 'leroy')
    path.write_text(json.dumps({**marker, 'synthetic_capacity_qualified': True}))
    with pytest.raises(AssertionError):
        original.verify_retained(folder, 'leroy')


@pytest.mark.parametrize('attempt', ['q', 'r', 't', 'u'])
@pytest.mark.parametrize('engine', ['leroy', 'jenkins'])
def test_fresh_transport_round_has_its_own_scope_and_cannot_be_diagnostic(engine, attempt):
    value = {**scope(), 'attempt': attempt, 'phase': 'rust-' + engine, 'engine': engine,
             'window': 'resource-window-day-20261015-' + attempt + '-rust-' + engine,
             'comparison_rounds': ['day-' + attempt + '-rust-' + engine + '-20261015']}
    if attempt in {'t', 'u'}:
        from nas_vm_dns import POLICY

        value['guest_dns_policy'] = POLICY
    original.validate_scope(value, value['comparison_rounds'][0], engine)
    with pytest.raises(AssertionError):
        original.validate_scope({**value, 'diagnostic_reference_only': True}, value['comparison_rounds'][0], engine)
    with pytest.raises(AssertionError):
        original.validate_scope(value, 'day-p-rust-' + engine + '-20261015', engine)


@pytest.fixture
def failed_reference():
    target = {'manifest': {'commit': original.vm.COMMIT,
        'runtimeImageId': 'sha256:6251c60f499e41e706613f931bf281ce52312b957d5a6a123cf4e27dd3242585',
        'files': {'verification-source.tar.gz': 'f0c737a8133cd73f6b34c66be5081316a7047a1881583532874b40abaec59708'}},
        'containers': [{'health': 'healthy'}] * 4}
    return {'run': {'id': 'e32366e7ffb249a4b7753d00ff6bd4c6', 'number': 179, 'status': 'failed',
        'reason': 'verify: Process exited with code 1', 'commit': original.vm.COMMIT, 'cancel_requested': False,
        'parameters': {'CHECK_GROUP': 'server-test'}, 'snapshot': {'source': {'application_patches_applied': False}}},
        'window': {**dict.fromkeys(('original_ci_terminal', 'restored_before_deadline',
            'all_seven_original_services_restored_healthy', 'infrastructure_unchanged', 'controller_process_unchanged',
            'controller_no_new_oom', 'health_verification_was_delayed_by_lost_administrative_access'), True),
            'original_rust_qualified': False, 'vm_running': False, 'healthy_before_deadline': False},
        'archive': {'source_removed': True, 'sha256': 'disk', 'copy_sha256': 'disk'},
        'restored': {'phase': 'restored'}, 'production': {'native_jenkins_quiet_during_window_verified': True,
            'changed_build_overlaps_test_window': False, 'production_modified': False},
        'plan': {'source_commit': original.vm.COMMIT, 'resource_profile': original.vm.DISK_QOS_FILE_MEMORY_PROFILE,
                 'script_sha256': {'physical.py': 'same'}},
        'memory': {'aligned_guest_host_samples': 707, 'minimum_host_available_kib': 3415512,
                   'minimum_host_swap_free_kib': 6144252}, 'target': target,
        'receipt': {'commit': original.vm.COMMIT, 'requestedGroup': 'server-test',
            'runId': 'd26c4c6fe1b54e4f8ca56f293d190ced', 'runtimeImageId': target['manifest']['runtimeImageId'],
            'sourceSha256': target['manifest']['files']['verification-source.tar.gz'], 'cancelled': False,
            'cleanupComplete': True, 'requestedPassed': False, 'checks': {'server-test': {'errorType': 'TimeoutExpired'}}}}


def test_failed_original_reference_allows_diagnosis_without_promoting_the_result(failed_reference):
    value = original.validate_failed_reference(failed_reference, {'physical.py': 'same'})
    assert value['diagnostic_reference_only'] and value['production_ready'] is False
    assert value['full_release_still_requires_both_successful_original_rust_runs']
    assert value['original_ci_results_reused'] is value['prior_health_before_deadline_verified'] is False
    plan = {**scope(), 'phase': 'rust-jenkins', 'engine': 'jenkins',
            'window': 'resource-window-day-20261015-p-rust-jenkins',
            'comparison_rounds': ['day-p-rust-jenkins-20261015'],
            'diagnostic_reference_only': True, 'failed_original_leroy_reference': value}
    original.validate_scope(plan, 'day-p-rust-jenkins-20261015', 'jenkins')


@pytest.mark.parametrize('path,value', [
    (('run', 'status'), 'running'), (('run', 'commit'), 'changed'),
    (('run', 'snapshot', 'source', 'application_patches_applied'), True),
    (('window', 'all_seven_original_services_restored_healthy'), False),
    (('window', 'vm_running'), True), (('window', 'restored_before_deadline'), False),
    (('window', 'health_verification_was_delayed_by_lost_administrative_access'), False),
    (('production', 'native_jenkins_quiet_during_window_verified'), False),
    (('production', 'changed_build_overlaps_test_window'), True),
    (('archive', 'source_removed'), False), (('archive', 'copy_sha256'), 'different'),
    (('restored', 'host_reserve_stop'), {'reason': 'swap'}),
    (('memory', 'minimum_host_swap_free_kib'), 2359295),
    (('receipt', 'cleanupComplete'), False), (('plan', 'script_sha256', 'physical.py'), 'changed'),
])
def test_failed_reference_rejects_unfinished_or_changed_conditions(failed_reference, path, value):
    data = copy.deepcopy(failed_reference)
    parent = data
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    with pytest.raises(AssertionError):
        original.validate_failed_reference(data, {'physical.py': 'same'})


@pytest.mark.parametrize('engine,phase,reference', [
    ('leroy', 'rust-leroy', True), ('jenkins', 'release-jenkins', True), ('jenkins', 'rust-jenkins', False),
])
def test_diagnostic_scope_cannot_expand_to_leroy_or_full_releases(engine, phase, reference):
    case = 'day-p-rust-' + engine + '-20261015' if phase.startswith('rust-') else 'day-p-release-20261015'
    value = {**scope(), 'engine': engine, 'phase': phase, 'window': 'resource-window-day-20261015-p-' + phase,
             'comparison_rounds': [case], 'diagnostic_reference_only': True,
             'failed_original_leroy_reference': {'diagnostic_reference_only': reference}}
    with pytest.raises(AssertionError):
        original.validate_scope(value, case, engine)
