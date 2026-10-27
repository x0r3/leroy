"""A failed Leroy run may require a Jenkins reference, never a release waiver."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_ci_background as background  # noqa: E402
import run_nas_day_window as day  # noqa: E402
from nas_vm_capacity_reference import PHYSICAL_SOURCES  # noqa: E402


@pytest.fixture
def evidence(monkeypatch):
    records = {
        'leroy-run.json': {'id': 'original-177', 'status': 'interrupted', 'cancel_requested': False,
            'reason': 'Runner lease expired; external effects require reconciliation', 'commit': day.vm.COMMIT,
            'parameters': {'CHECK_GROUP': 'server-test'}, 'snapshot': {'source': {'application_patches_applied': False}}},
        'window-result.json': {**dict.fromkeys(('all_seven_original_services_restored_healthy', 'healthy_before_deadline',
            'native_jenkins_quiet', 'infrastructure_unchanged', 'controller_process_unchanged', 'controller_no_new_oom'), True),
            'original_rust_qualified': False},
        'closed-disk-archive.json': {'source_removed': True}, 'restored-window.json': {},
        'approval.json': {'resource_profile': day.vm.DISK_QOS_FILE_MEMORY_PROFILE,
                          'script_sha256': dict.fromkeys(PHYSICAL_SOURCES, 'same')},
        'leroy-memory-summary.json': {'aligned_guest_host_samples': 155,
            'minimum_host_available_kib': 3348748, 'minimum_host_swap_free_kib': 5605664},
        'leroy-target-before.json': {'manifest': {'commit': day.vm.COMMIT,
            'runtimeImageId': 'sha256:6251c60f499e41e706613f931bf281ce52312b957d5a6a123cf4e27dd3242585',
            'files': {'verification-source.tar.gz': 'f0c737a8133cd73f6b34c66be5081316a7047a1881583532874b40abaec59708'}},
            'containers': [{'health': 'healthy'}] * 4},
        'leroy-file-memory-capacity.json': {'qualified_synthetic_capacity': True, 'all_page_markers_intact': True,
                                          'allocated_mib': 5888, 'hold_seconds': 60},
    }
    monkeypatch.setattr(day, 'read', lambda path: copy.deepcopy(records[path.name]))
    monkeypatch.setattr(day.vm, 'digest', lambda path: 'same')
    return records


def test_interrupted_reference_is_explicitly_diagnostic_and_bound(evidence):
    value = day.interrupted_reference_binding()
    assert day.interrupted_reference('rust-jenkins', 'g')
    assert value['diagnostic_reference_only'] and value['production_ready'] is False
    assert value['full_release_still_requires_both_successful_original_rust_runs']
    assert value['interrupted_leroy_run_id'] == 'original-177'
    assert value['equal_background_load_proven'] is False


@pytest.mark.parametrize('file,key,value', [
    ('leroy-run.json', 'cancel_requested', True), ('leroy-run.json', 'reason', 'Different failure'),
    ('leroy-run.json', 'status', 'running'), ('closed-disk-archive.json', 'source_removed', False),
    ('window-result.json', 'all_seven_original_services_restored_healthy', False),
    ('window-result.json', 'native_jenkins_quiet', False), ('window-result.json', 'controller_no_new_oom', False),
    ('leroy-memory-summary.json', 'minimum_host_swap_free_kib', 2359295),
])
def test_reference_never_bypasses_changed_conditions(evidence, file, key, value):
    evidence[file][key] = value
    with pytest.raises(AssertionError):
        day.interrupted_reference_binding()


@pytest.mark.parametrize('attempt', ['g', 'h'])
def test_full_release_still_requires_leroy_rust_success(monkeypatch, attempt):
    monkeypatch.setattr(day, 'ATTEMPT', attempt)
    monkeypatch.setattr(day, 'read', lambda path: {'all_seven_original_services_restored_healthy': True, 'source_removed': True})
    monkeypatch.setattr(background, 'capacity_proof', lambda: 'proof')
    monkeypatch.setattr(day, 'interrupted_reference_binding', lambda: pytest.fail('No full-release reference waiver'))

    def missing(engine):
        assert engine == 'leroy'
        raise AssertionError('Leroy original Rust did not succeed')

    monkeypatch.setattr(day, 'require_day_rust', missing)
    for phase in ('release-leroy', 'release-jenkins'):
        with pytest.raises(AssertionError, match='original Rust'):
            day.prerequisites(phase)


@pytest.fixture
def failed_observer(evidence):
    evidence['window-result.json'].update(outcome='stopped:original_jenkins_status_ssh_timeout', diagnostic_reference_only=True)
    evidence['stage-result.json'] = {'exit_code': 1}
    evidence['aborted-original-ci-collection.json'] = {
        'original_ci_terminal': True, 'original_ci_restarted': False, 'new_pipeline_dispatched': False,
        'test_completion_claimed': False, 'operator_stop_to_finish_observer_failure_cleanup': True, 'number': 28}
    evidence['jenkins-build.json'] = {'number': 28, 'building': False, 'result': 'ABORTED', 'checkout_revisions': [day.vm.COMMIT]}
    evidence['approval.json']['source_commit'] = day.vm.COMMIT
    return evidence


def test_new_reference_is_bound_to_aborted_original_observer_attempt(failed_observer):
    value = day.failed_observer_reference_binding()
    assert value['reference_case'] == 'day-g-rust-jenkins-20261015' and value['original_job'] == 28
    assert value['diagnostic_reference_only'] and not value['original_ci_results_reused'] and not value['production_ready']
    assert day.interrupted_reference('rust-jenkins', 'h')
    assert not day.interrupted_reference('release-jenkins', 'h')


@pytest.mark.parametrize('file,key,value', [
    ('window-result.json', 'outcome', 'different failure'),
    ('window-result.json', 'original_rust_qualified', True),
    ('window-result.json', 'all_seven_original_services_restored_healthy', False),
    ('stage-result.json', 'exit_code', 0),
    ('aborted-original-ci-collection.json', 'original_ci_restarted', True),
    ('aborted-original-ci-collection.json', 'new_pipeline_dispatched', True),
    ('jenkins-build.json', 'number', 29),
    ('jenkins-build.json', 'building', True),
    ('jenkins-build.json', 'checkout_revisions', ['changed']),
])
def test_new_reference_rejects_missing_recovery_or_changed_original(failed_observer, file, key, value):
    failed_observer[file][key] = value
    with pytest.raises(AssertionError):
        day.failed_observer_reference_binding()
