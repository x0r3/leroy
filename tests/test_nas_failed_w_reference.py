"""A failed reference permits one comparison, without relaxing release gates."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_failed_w_reference as failed  # noqa: E402
import nas_resource_window_guard as guard  # noqa: E402
import run_nas_day_window as day  # noqa: E402


@pytest.fixture
def negative():
    return {'run': {'id': failed.RUN, 'number': 186, 'status': 'failed', 'cancel_requested': False,
        'reason': 'verify: Process exited with code 1', 'commit': failed.vm.COMMIT,
        'parameters': {'CHECK_GROUP': 'server-test'},
        'snapshot': {'source': {'application_patches_applied': False}}},
        'window': {'phase': 'rust-leroy', 'original_rust_qualified': False, 'outcome': 'stopped:AssertionError',
            **{k: True for k in ('all_seven_original_services_restored_healthy', 'healthy_before_deadline',
                'native_jenkins_quiet', 'infrastructure_unchanged', 'controller_process_unchanged', 'controller_no_new_oom')}},
        'archive': {'source_removed': True, 'copy_sha256': 'same', 'sha256': 'same'},
        'restored': {'phase': 'restored'}, 'memory': {'released_after_vm_stopped': True},
        'prepared': {'commit': failed.vm.COMMIT, 'parameters': {'CHECK_GROUP': 'server-test'},
            'resource_profile': failed.vm.DISK_QOS_FILE_MEMORY_PROFILE, 'original_workload_qualification': True,
            'synthetic_capacity_qualified': False, 'matching_ci_background': True, 'ci_slots': 2},
        'target': {'manifest': {'commit': failed.vm.COMMIT, 'runtimeImageId': 'runtime',
            'files': {'verification-source.tar.gz': 'source'}, 'build': {'timestamp': 'stamp'}}},
        'receipt': {'commit': failed.vm.COMMIT, 'requestedGroup': 'server-test', 'runId': failed.BACKEND_RUN,
            'runtimeImageId': 'runtime', 'sourceSha256': 'source', 'buildTimestamp': 'stamp',
            'activeRelease': True, 'cleanupComplete': True, 'cancelled': False,
            'requestedPassed': False, 'checks': {'server-test': {'passed': False}}},
        'rust': {'expectedTests': 0, 'measuredTests': 0, 'complete': False}}


def test_failure_stays_negative_and_requires_fresh_original_comparison(negative):
    proof = failed.validate(negative)
    assert proof['diagnostic_reference_only'] and not proof['production_ready']
    assert not proof['original_ci_results_reused'] and not proof['offline_receipt_is_original_ci_artifact']
    assert proof['full_release_still_requires_both_successful_original_rust_runs']


@pytest.mark.parametrize('section,key,value', [
    ('run', 'status', 'succeeded'), ('run', 'cancel_requested', True),
    ('window', 'native_jenkins_quiet', False), ('window', 'healthy_before_deadline', False),
    ('archive', 'copy_sha256', 'corrupt'), ('archive', 'source_removed', False),
    ('restored', 'host_reserve_stop', True), ('memory', 'released_after_vm_stopped', False),
    ('receipt', 'cleanupComplete', False), ('receipt', 'runtimeImageId', 'changed'),
    ('rust', 'complete', True), ('rust', 'measuredTests', 1),
])
def test_incomplete_or_reinterpreted_evidence_cannot_admit_counterpart(negative, section, key, value):
    changed = copy.deepcopy(negative)
    changed[section][key] = value
    with pytest.raises(AssertionError):
        failed.validate(changed)


def test_diagnostic_attempt_registers_only_original_jenkins_rust():
    assert day.window_name('rust-jenkins', 'y') in guard.DAY_WINDOWS
    for phase in ('rust-leroy', 'release-leroy', 'release-jenkins'):
        assert day.window_name(phase, 'y') not in guard.DAY_WINDOWS
        with pytest.raises(AssertionError):
            day.validate_approval({'attempt': 'y', 'phase': phase, 'user_approved': True,
                                   'diagnostic_reference_only': True})


def test_imported_validator_selects_explicit_reference_not_module_default(monkeypatch):
    monkeypatch.setattr(day, 'ATTEMPT', 'a')
    monkeypatch.setattr(failed, 'binding', lambda: {'reference': 'failed-W'})
    assert day.failed_original_reference_binding('y') == {'reference': 'failed-W'}


def test_corrected_admission_uses_new_unit_identity(monkeypatch):
    import nas_acceptance_service as service

    monkeypatch.setattr(service, 'ATTEMPT', 'y')
    monkeypatch.setattr(service, 'INSTANCE', 'y2')
    assert service.unit_name('rust-jenkins') == 'leroy-acceptance-20261017-y2-rust-jenkins'


def test_diagnostic_result_cannot_satisfy_full_rust_gate(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(day, 'ATTEMPT', 'y')
    monkeypatch.setattr(day, 'BASE', tmp_path)
    monkeypatch.setattr(day, 'require_rust_evidence', lambda *_: {'requested_passed': True})
    folder = tmp_path / day.window_name('rust-jenkins')
    folder.mkdir()
    (folder / 'window-result.json').write_text(json.dumps({'diagnostic_reference_only': True}))
    with pytest.raises(AssertionError, match='Diagnostic reference cannot qualify full release'):
        day.require_day_rust('jenkins')
