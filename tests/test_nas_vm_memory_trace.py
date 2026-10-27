"""Missing or stale guest samples cannot establish simultaneous memory headroom."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from nas_vm_memory_trace import summarize  # noqa: E402


def row(*, guest_at=11, guest=True):
    value = {'host_before': {'at': 10, 'memory_kib': {'MemAvailable': 500, 'SwapFree': 900}},
             'host_after': {'at': 12, 'memory_kib': {'MemAvailable': 400, 'SwapFree': 800}, 'vmstat': {'oom_kill': 3}},
             'owned_vm_cgroup': {'memory.current': '3000', 'memory.swap.current': '2000'},
             'qemu': [{'memory_kib': {'Rss': 2, 'Swap': 1}}]}
    if guest:
        value['guest'] = {'at': guest_at, 'memory_kib': {'MemAvailable': 700, 'MemFree': 600}, 'vmstat': {'oom_kill': 0}}
    else:
        value['guest_error'] = 'timeout_or_invalid_json'
    return value


def test_gaps_and_stale_guest_clocks_are_reported_without_inventing_headroom():
    result = summarize([row(guest=False), row(guest_at=1)])
    assert result['aligned_guest_host_samples'] == 0
    assert result['guest_observation_errors'] == 1
    assert result['guest_unaligned_or_missing_samples'] == 2
    assert result['minimum_aligned_guest_available_kib'] is None
    assert result['guest_oom_kill_counters'] == []


def test_host_vm_and_guest_memory_are_distinct_and_both_host_boundaries_count():
    result = summarize([row()])
    assert result['aligned_guest_host_samples'] == 1
    assert result['minimum_host_available_kib'] == 400
    assert result['minimum_host_swap_free_kib'] == 800
    assert result['peak_owned_vm_swap_bytes'] == 2000
    assert result['minimum_aligned_guest_free_kib'] == 600
    assert result['guest_oom_kill_counters'] == [0]
    assert result['physical_nas_oom_kill_counters'] == [3]
    assert not result['memory_trace_alone_proves_test_completion']


def test_slow_sample_cannot_prove_alignment():
    value = row()
    value['host_after']['at'] = 30
    assert summarize([value])['aligned_guest_host_samples'] == 0


def test_absent_observations_are_not_a_success():
    with pytest.raises(ValueError):
        summarize([])


@pytest.mark.parametrize('error', [RuntimeError('private failure details'), OSError('private path')])
def test_observer_collection_failure_does_not_raise_and_never_certifies_memory(monkeypatch, tmp_path, error):
    import json

    import diagnose_nas_release_group as diagnosis
    import nas_vm_memory_trace as trace

    def unavailable(*_):
        raise error

    monkeypatch.setattr(trace, 'collect_trace', unavailable)
    assert diagnosis.collect_memory_evidence(tmp_path, 'leroy') is False
    saved = tmp_path.joinpath('leroy-memory-collection-error.json').read_text()
    assert 'private' not in saved
    proof = json.loads(saved)
    assert not proof['memory_evidence_complete'] and not proof['original_ci_restarted']
    assert not tmp_path.joinpath('leroy-memory-summary.json').exists()
