"""Actual original workloads must qualify both engines before the full releases."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_nas_original_night_window as original  # noqa: E402


@pytest.mark.parametrize('engines,allowed', [
    ({}, False), ({'leroy': True}, False), ({'jenkins': True}, False),
    ({'leroy': True, 'jenkins': False}, False), ({'leroy': False, 'jenkins': True}, False),
    ({'leroy': True, 'jenkins': 'succeeded'}, False), ({'leroy': True, 'jenkins': True}, True),
])
def test_full_release_requires_two_actual_qualifications(engines, allowed):
    assert original.full_release_allowed(engines) is allowed


def test_bounded_trial_never_turns_partial_synthetic_capacity_into_success(monkeypatch):
    def evidence(case):
        return {'reason': 'conservative_host_admission_declined', 'qualified_synthetic_capacity': False,
                'peak_allocated_mib': 5632 if '4096' in case.name else 5120,
                'memory_summary': {'minimum_host_available_kib': 400 * 1024,
                    'minimum_host_swap_free_kib': 2500 * 1024, 'guest_oom_kill_counters': [0],
                    'physical_nas_oom_kill_counters': [3]}}
    monkeypatch.setattr(original, 'capacity_evidence', evidence)
    monkeypatch.setattr(original, 'read', lambda p: {'native_jenkins_quiet_window_verified': True})
    profile, decision = original.select_profile()
    assert profile.endswith('4096')
    assert not decision['synthetic_maximum_qualified'] and not decision['original_workload_qualified']


def test_no_trial_without_explicit_overnight_authorization(monkeypatch, tmp_path):
    monkeypatch.setattr(original, 'PLAN', tmp_path)
    monkeypatch.setattr(original, 'read', lambda p: pytest.fail('No window inspection before approval'))
    with pytest.raises(AssertionError, match='Explicit overnight'):
        original.run()


def test_measured_ram_guard_failure_selects_lower_resident_vm_budget(monkeypatch):
    monkeypatch.setattr(original, 'ATTEMPT', 'c')
    monkeypatch.setattr(original, 'capacity_evidence', lambda p: {
        'reason': 'conservative_host_admission_declined', 'qualified_synthetic_capacity': False,
        'peak_allocated_mib': 5632 if '4096' in p.name else 5120,
        'memory_summary': {'minimum_host_available_kib': 400 * 1024,
            'minimum_host_swap_free_kib': 2500 * 1024, 'guest_oom_kill_counters': [0],
            'physical_nas_oom_kill_counters': [3]}})

    def read(path):
        if path.name == 'final-state.json':
            return {'original_ci_terminal': True}
        if path.name == 'owned-vm-resource-guard.json':
            return {'resource_guard': {'host_memory_kib': {'MemAvailable': 83 * 1024},
                                      'minimum_host_memory_kib': {'MemAvailable': 128 * 1024}}}
        return {'native_jenkins_quiet_window_verified': True}

    monkeypatch.setattr(original, 'read', read)
    profile, decision = original.select_profile()
    assert profile.endswith('3584') and not decision['synthetic_maximum_qualified']


def test_actual_ram_and_swap_stops_select_intermediate_budget(monkeypatch):
    monkeypatch.setattr(original, 'ATTEMPT', 'd')
    monkeypatch.setattr(original, 'capacity_evidence', lambda p: {
        'reason': 'conservative_host_admission_declined', 'qualified_synthetic_capacity': False,
        'peak_allocated_mib': 5632 if '4096' in p.name else 5120,
        'memory_summary': {'minimum_host_available_kib': 400 * 1024,
            'minimum_host_swap_free_kib': 2500 * 1024, 'guest_oom_kill_counters': [0],
            'physical_nas_oom_kill_counters': [3]}})

    def read(path):
        if path.name == 'final-state.json':
            return {'original_ci_terminal': True}
        if path.name == 'owned-vm-resource-guard.json':
            if 'original-night-c-' in path.parent.name:
                return {'host_memory_kib': {'MemAvailable': 708 * 1024, 'SwapFree': 2297 * 1024}}
            return {'resource_guard': {'host_memory_kib': {'MemAvailable': 83 * 1024},
                                      'minimum_host_memory_kib': {'MemAvailable': 128 * 1024}}}
        return {'native_jenkins_quiet_window_verified': True}

    monkeypatch.setattr(original, 'read', read)
    profile, decision = original.select_profile()
    assert profile.endswith('3840') and not decision['synthetic_maximum_qualified']
