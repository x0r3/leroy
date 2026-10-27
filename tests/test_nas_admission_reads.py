"""Unknown read responses must never become admission or duplicate allocation."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_followup_support as support  # noqa: E402
import nas_vm_file_capacity as capacity  # noqa: E402


@pytest.mark.parametrize('error', [capacity.vm.SSHTransportUnavailable('unknown'), subprocess.TimeoutExpired('read', 15)])
def test_unavailable_read_retries_same_operation_without_allocating(monkeypatch, tmp_path, error):
    now = [100]
    monkeypatch.setattr(capacity.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(capacity.time, 'sleep', lambda seconds: now.__setitem__(0, now[0] + seconds))
    calls = []

    def read(timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise error
        return {'active_builds': ['new-production-build']}

    assert capacity.admission_read(tmp_path, 'leroy', 'production_jobs', read, 160)['active_builds']
    assert calls == [15, 15]
    row = json.loads((tmp_path / 'leroy-capacity-read-unknown.jsonl').read_text())
    assert row['outcome_unknown'] and row['allocation_repeated'] is False


@pytest.mark.parametrize('error', [RuntimeError('Identity conflict'), ValueError('Invalid response')])
def test_identity_and_response_failures_are_not_retried(tmp_path, error):
    calls = []

    def read(timeout):
        calls.append(timeout)
        raise error

    with pytest.raises(type(error)):
        capacity.admission_read(tmp_path, 'leroy', 'read', read, capacity.time.monotonic() + 60)
    assert len(calls) == 1


def test_admission_budget_is_fixed_and_shared_between_reads(monkeypatch, tmp_path):
    now = [100]
    monkeypatch.setattr(capacity.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(capacity.time, 'sleep', lambda seconds: now.__setitem__(0, now[0] + seconds))
    calls = []

    def missing(timeout):
        calls.append(timeout)
        now[0] += timeout
        raise capacity.vm.SSHTransportUnavailable('unknown')

    with pytest.raises(TimeoutError, match='do not allocate'):
        capacity.admission_read(tmp_path, 'leroy', 'production_jobs', missing, 160)
    assert now[0] == 160 and calls == [15, 15, 15]
    with pytest.raises(TimeoutError):
        capacity.admission_read(tmp_path, 'leroy', 'host_memory', lambda timeout: pytest.fail('Expired shared budget'), 160)


@pytest.mark.parametrize('code,diagnostic,exception', [
    (255, 'Connection timed out during banner exchange', capacity.vm.SSHTransportUnavailable),
    (1, 'AssertionError: Production identity changed', RuntimeError),
])
def test_production_reader_preserves_transport_and_identity_distinction(monkeypatch, code, diagnostic, exception):
    monkeypatch.setattr(support, 'production_prelude', lambda: '# pinned read-only production data\n')
    calls = []

    def run(*args, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess([], code, '', diagnostic)

    monkeypatch.setattr(support, 'run_script', run)
    with pytest.raises(exception):
        support.production_jobs(history=False, timeout=10)
    assert calls[0]['timeout'] == 10 and calls[0]['sudo'] is True


def test_changed_production_after_lost_observation_prevents_first_allocation(monkeypatch, tmp_path):
    monkeypatch.setattr(capacity.vm, 'RESOURCE_PROFILE', capacity.vm.FILE_MEMORY_PROFILE)
    monkeypatch.setattr(capacity.vm, 'ROUND', tmp_path.name)
    monkeypatch.setattr(capacity.vm, 'ROOT', tmp_path)
    (tmp_path / 'leroy-memory-trace.json').write_text('{}')
    scenario = tmp_path / 'test-results/nas-parity/followup/candidates/graphato' / capacity.vm.COMMIT / 'scenarios/root-private-existing-host/scenario.json'
    scenario.parent.mkdir(parents=True)
    scenario.write_text(json.dumps({'baseline_release': {'runtimeImageId': 'sha256:test'}}))
    reads = iter([{'active_builds': [], 'jobs': {'production': 1}},
                  capacity.vm.SSHTransportUnavailable('unknown'),
                  {'active_builds': [], 'jobs': {'production': 2}}])

    def jobs(**kwargs):
        row = next(reads)
        if isinstance(row, Exception):
            raise row
        return row

    monkeypatch.setattr(capacity, 'production_jobs', jobs)
    monkeypatch.setattr(capacity.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(capacity.vm, 'guest', lambda *args, **kwargs: '{}')
    actions = []
    monkeypatch.setattr(capacity, 'control', lambda action: actions.append(action))
    with pytest.raises(AssertionError):
        capacity.qualify(tmp_path, 'leroy')
    assert actions == [{'action': 'stop'}]
