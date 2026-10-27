"""Supplemental capacity evidence must never reuse a stressed application VM."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_vm_capacity_reference as reference  # noqa: E402


@pytest.fixture
def evidence(monkeypatch, tmp_path):
    vm = reference.vm
    monkeypatch.setattr(vm, 'ROOT', tmp_path)
    monkeypatch.setattr(vm, 'RESOURCE_PROFILE', vm.PROTECTED_FILE_MEMORY_PROFILE)
    base = tmp_path / 'test-results/nas-parity/followup'

    def put(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    sources = {}
    for name in reference.PHYSICAL_SOURCES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('qualified physical environment')
        sources[name] = vm.digest(path)
    put(base / 'day-window-plan-20261015-e-rust-leroy/approval.json', {
        'source_commit': vm.COMMIT, 'resource_profile': vm.RESOURCE_PROFILE, 'script_sha256': sources})
    case = base / reference.REFERENCE
    window = base / 'resource-window-day-20261015-e-rust-leroy'
    put(case / 'prepared.json', {'commit': vm.COMMIT, 'resource_profile': vm.RESOURCE_PROFILE})
    put(window / 'window-result.json', dict.fromkeys(('all_seven_original_services_restored_healthy',
        'native_jenkins_quiet', 'infrastructure_unchanged', 'controller_process_unchanged', 'controller_no_new_oom'), True))
    put(window / 'closed-disk-archive.json', {'source_removed': True})
    put(window / 'restored-window.json', {})
    put(case / 'no-original-ci-dispatch.json', {'original_ci_dispatched': False})
    put(case / 'leroy-memory-summary.json', {'aligned_guest_host_samples': 17,
        'minimum_host_available_kib': 3199416, 'minimum_host_swap_free_kib': 5567096})
    put(case / 'leroy-file-memory-capacity.json', {
        'qualified_synthetic_capacity': True, 'all_page_markers_intact': True, 'allocated_mib': 5888,
        'hold_seconds': 60, 'original_fixture_limits_emulated': True, 'original_ci_dispatched': False,
        'application_source_or_tests_changed': False,
        'limits': {'memory_bytes': 6 * 1024**3, 'memory_and_swap_bytes': 6 * 1024**3,
                   'nano_cpus': 2 * 10**9, 'cgroup_swap_max': 0,
                   'image': 'sha256:6251c60f499e41e706613f931bf281ce52312b957d5a6a123cf4e27dd3242585'},
        'phases': [{'kind': 'allocated', 'allocated_mib': 5888, 'at_epoch': 0},
                   *[{'kind': 'held', 'allocated_mib': 5888, 'at_epoch': at} for at in (20, 40, 60)],
                   {'kind': 'stopped', 'all_page_markers_intact': True}]})
    return base, case, window, put


def test_reference_explicitly_reports_separate_vm_and_failed_application_health(evidence, tmp_path):
    value = reference.binding()
    assert value['fresh_application_baseline_required'] is True
    assert value['capacity_test_executed_in_current_guest'] is False
    assert value['original_ci_results_reused'] is False
    assert value['reference_application_health_failed'] is True
    fresh = tmp_path / 'fresh-original'
    fresh.mkdir()
    assert reference.retain(fresh, 'leroy') == value
    assert reference.retain(fresh, 'leroy') == value


@pytest.mark.parametrize('filename,key,value', [
    ('leroy-file-memory-capacity.json', 'all_page_markers_intact', False),
    ('leroy-file-memory-capacity.json', 'hold_seconds', 59),
    ('leroy-file-memory-capacity.json', 'allocated_mib', 5632),
    ('no-original-ci-dispatch.json', 'original_ci_dispatched', True),
    ('leroy-memory-summary.json', 'minimum_host_swap_free_kib', 2359295),
    ('prepared.json', 'resource_profile', 'another-profile'),
])
def test_reference_rejects_incomplete_capacity_overlap_or_changed_profile(evidence, filename, key, value):
    _, case, _, put = evidence
    path = case / filename
    data = reference.read(path)
    data[key] = value
    put(path, data)
    with pytest.raises(AssertionError):
        reference.binding()


def test_reference_rejects_changed_physical_code_or_unrestored_services(evidence):
    base, _, window, put = evidence
    put(window / 'window-result.json', {'all_seven_original_services_restored_healthy': False})
    with pytest.raises(AssertionError):
        reference.binding()
    source = reference.vm.ROOT / reference.PHYSICAL_SOURCES[0]
    source.write_text('changed VM configuration')
    with pytest.raises(AssertionError, match='environment code changed'):
        reference.binding()
