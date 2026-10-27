"""A lost registration response cannot cancel or redispatch the original stage."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_nas_day_window as day  # noqa: E402


@pytest.mark.parametrize('failure', [subprocess.TimeoutExpired('secret SSH argv', 420), OSError('secret path'),
                                      json.JSONDecodeError('secret partial snapshot', '{', 0)])
@pytest.mark.parametrize('fault_at', ['register-runs', 'register-vm'])
def test_unknown_response_observes_the_same_stage_and_journal(monkeypatch, tmp_path, failure, fault_at):
    approval = {'absolute_deadline_epoch': 10000}
    polls = iter([None, None, 0])
    process = SimpleNamespace(poll=lambda: next(polls), terminate=lambda: pytest.fail('Do not cancel the original stage'))
    monkeypatch.setattr(day, 'validate_approval', lambda value: None)
    monkeypatch.setattr(day.time, 'time', lambda: 1000)
    monkeypatch.setattr(day.time, 'sleep', lambda value: None)
    monkeypatch.setattr(day.subprocess, 'Popen', lambda *a, **kw: pytest.fail('Never redispatch CI'))
    calls = []

    def register(remote, case):
        assert remote == 'same-journal' and case == tmp_path / 'same-case'
        calls.append('register-runs')
        if fault_at == 'register-runs' and len(calls) == 1:
            raise failure

    def action(remote, operation):
        assert (remote, operation) == ('same-journal', 'register-vm')
        calls.append('register-vm')
        if fault_at == 'register-vm' and calls.count('register-vm') == 1:
            raise failure
        return {'phase': 'paused', 'deadline': approval['absolute_deadline_epoch']}

    monkeypatch.setattr(day, 'register_runs', register)
    monkeypatch.setattr(day, 'action', action)
    day.observe_original_stage(process, approval, 'same-journal', tmp_path / 'same-case', tmp_path)
    assert calls.count('register-runs') == 2
    assert calls.count('register-vm') == (1 if fault_at == 'register-runs' else 2)
    error = json.loads((tmp_path / 'stage-observation-errors.jsonl').read_text())
    assert error['outcome_unknown'] and not error['original_ci_restarted']
    assert 'secret' not in json.dumps(error)
    assert json.loads((tmp_path / 'latest-window-state.json').read_text())['deadline'] == 10000


def test_unknown_response_cannot_extend_the_recovery_margin(monkeypatch, tmp_path):
    now = [1000]
    calls = []
    monkeypatch.setattr(day, 'validate_approval', lambda value: None)
    monkeypatch.setattr(day.time, 'time', lambda: now[0])
    monkeypatch.setattr(day.time, 'sleep', lambda value: pytest.fail('Recovery margin has already begun'))
    monkeypatch.setattr(day, 'register_runs', lambda *args: None)

    def action(remote, operation):
        calls.append((remote, operation))
        now[0] = 1100
        raise subprocess.TimeoutExpired('SSH', 60)

    monkeypatch.setattr(day, 'action', action)
    with pytest.raises(AssertionError, match='fixed recovery margin'):
        day.observe_original_stage(SimpleNamespace(poll=lambda: None),
                                   {'absolute_deadline_epoch': 2000}, 'same-journal', tmp_path, tmp_path)
    assert calls == [('same-journal', 'register-vm')]


@pytest.mark.parametrize('state', [
    {'phase': 'restored', 'deadline': 10000},
    {'phase': 'paused', 'deadline': 10001},
])
def test_changed_scope_or_finished_window_is_not_treated_as_a_transport_gap(monkeypatch, tmp_path, state):
    monkeypatch.setattr(day, 'validate_approval', lambda value: None)
    monkeypatch.setattr(day.time, 'time', lambda: 1000)
    monkeypatch.setattr(day, 'register_runs', lambda *args: None)
    monkeypatch.setattr(day, 'action', lambda *args: state)
    with pytest.raises(AssertionError):
        day.observe_original_stage(SimpleNamespace(poll=lambda: None),
                                   {'absolute_deadline_epoch': 10000}, 'same-journal', tmp_path, tmp_path)
