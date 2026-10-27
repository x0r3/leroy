"""Diagnostic lifecycle errors may never stop an unchanged original release."""

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_optional_observer as observer  # noqa: E402


def test_full_stage_can_finish_before_its_caller_stops_vm(monkeypatch, tmp_path):
    (tmp_path / 'worker-control-trace.json').write_text('{}')
    monkeypatch.setattr(observer.vm, 'state', lambda: {'State': {'Running': True}})
    monkeypatch.setattr(observer, 'collect_worker_trace', lambda p: pytest.fail('No trace transfer under original VM load'))
    assert observer.collect_optional_trace(tmp_path)['status'] == 'deferred_until_vm_shutdown'
    assert not (tmp_path / 'worker-control-trace-collection.json').exists()


def test_collects_once_after_shutdown(monkeypatch, tmp_path):
    (tmp_path / 'worker-control-trace.json').write_text('{}')
    monkeypatch.setattr(observer.vm, 'state', lambda: {'State': {'Running': False}})
    calls = []
    monkeypatch.setattr(observer, 'collect_worker_trace', lambda p: calls.append(p) or {'outcome': 'worker_exited'})
    first = observer.collect_optional_trace(tmp_path)
    assert first['status'] == 'collected'
    assert observer.collect_optional_trace(tmp_path) == first and calls == [tmp_path]


def test_failure_remains_optional_and_retains_only_exception_type(monkeypatch, tmp_path):
    (tmp_path / 'worker-control-trace.json').write_text('{}')
    monkeypatch.setattr(observer.vm, 'state', lambda: {'State': {'Running': False}})

    def fail(_):
        raise RuntimeError('secret-token-in-an-exception')

    monkeypatch.setattr(observer, 'collect_worker_trace', fail)
    result = observer.collect_optional_trace(tmp_path)
    assert result['status'] == 'observation_failed' and result['error_type'] == 'RuntimeError'
    assert 'secret-token' not in json.dumps(result)


def test_no_observer_requires_no_nas_probe(monkeypatch, tmp_path):
    monkeypatch.setattr(observer.vm, 'state', lambda: pytest.fail('Unnecessary remote read'))
    assert observer.collect_optional_trace(tmp_path) == {'status': 'not_started'}


def test_completed_original_stage_does_not_require_its_callers_vm_shutdown(monkeypatch, tmp_path):
    import run_nas_original_night_window as original

    case = tmp_path / 'case'
    case.mkdir()
    (case / 'worker-control-trace.json').write_text('{}')
    monkeypatch.setattr(original, 'DEADLINE', time.time() + 3600)
    monkeypatch.setattr(original, 'require_approval', lambda: None)
    monkeypatch.setattr(original, 'idle', lambda: None)
    monkeypatch.setattr(original, 'register_runs', lambda *args: None)
    monkeypatch.setattr(original, 'action', lambda *args: {'phase': 'paused', 'deadline': original.DEADLINE})
    monkeypatch.setattr(original.subprocess, 'Popen', lambda *args, **kwargs:
                        SimpleNamespace(pid=123, returncode=0, poll=lambda: 0))
    monkeypatch.setattr(observer.vm, 'state', lambda: {'State': {'Running': True}})
    monkeypatch.setattr(observer, 'collect_worker_trace', lambda folder: pytest.fail('No transfer during original CI'))

    original.stage(tmp_path, 'unused', 'full-release-leroy', ['unused'], case=case)

    assert json.loads((tmp_path / 'full-release-leroy-result.json').read_text())['exit_code'] == 0
    assert not (case / 'worker-control-trace-collection.json').exists()
