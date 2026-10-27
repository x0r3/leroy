"""Only qualified transport loss may use existing idempotent observation retries."""
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_release_vm as vm  # noqa: E402
import run_nas_day_window as day  # noqa: E402


@pytest.mark.parametrize('diagnostic', [
    'Connection timed out during banner exchange',
    'Connection to 192.168.178.97 port 22 timed out',
    'Timeout, server 192.168.178.97 not responding.',
    'ssh: connect to host 192.168.178.97 port 22: Connection refused',
    'Connection reset by 192.168.178.97 port 22',
    'Connection closed by 192.168.178.97 port 22',
    'kex_exchange_identification: read: Connection reset by peer',
    'client_loop: send disconnect: Broken pipe',
    'kex_exchange_identification: read: Unknown error\n'
    'banner exchange: Connection to 192.168.178.97 port 22: Unknown error',
])
def test_transport_result_remains_unknown_and_does_not_expose_output(monkeypatch, diagnostic):
    result = subprocess.CompletedProcess([], 255, 'partial private response', diagnostic)
    monkeypatch.setattr(vm, 'run_script', lambda *args, **kwargs: result)
    with pytest.raises(vm.SSHTransportUnavailable) as error:
        vm.remote('already_authorized_action()')
    assert isinstance(error.value, OSError)
    assert 'outcome is unknown' in str(error.value)
    assert 'private' not in str(error.value) and diagnostic not in str(error.value)


@pytest.mark.parametrize('code,diagnostic', [
    (1, 'Connection timed out during banner exchange'),
    (255, 'Permission denied (publickey,password).'),
    (255, 'Host key verification failed.'),
    (1, 'AssertionError: Retained process identity changed'),
    (255, 'Unrecognized failure'),
    (255, 'kex_exchange_identification: read: Unknown error'),
    (255, 'banner exchange: Connection to other.invalid port 22: Unknown error'),
])
def test_permission_identity_and_unknown_failures_remain_fatal(monkeypatch, code, diagnostic):
    monkeypatch.setattr(vm, 'run_script', lambda *args, **kwargs: subprocess.CompletedProcess([], code, '', diagnostic))
    with pytest.raises(RuntimeError):
        vm.remote('reviewed_action()')


def test_day_registration_keeps_same_process_after_actual_ssh_wrapper_failure(monkeypatch, tmp_path):
    calls = []
    polls = iter([None, None, 0])
    process = SimpleNamespace(poll=lambda: next(polls))
    results = iter([subprocess.CompletedProcess([], 255, '', 'Connection timed out during banner exchange'),
                    subprocess.CompletedProcess([], 0, '{"phase":"paused","deadline":2000}', '')])
    monkeypatch.setattr(vm, 'run_script', lambda *args, **kwargs: next(results))
    monkeypatch.setattr(day, 'validate_approval', lambda approval: None)
    monkeypatch.setattr(day.time, 'time', lambda: 1000)
    monkeypatch.setattr(day.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(day, 'register_runs', lambda remote, case: calls.append((remote, case)))
    day.observe_original_stage(process, {'absolute_deadline_epoch': 2000}, 'same-journal', tmp_path, tmp_path)
    assert calls == [('same-journal', tmp_path)] * 2
    row = (tmp_path / 'stage-observation-errors.jsonl').read_text()
    assert 'SSHTransportUnavailable' in row and '"original_ci_restarted": false' in row


def test_recovery_retries_same_journal_when_ssh_response_is_lost(monkeypatch, tmp_path):
    calls = []
    results = iter([subprocess.CompletedProcess([], 255, '', 'Timeout, server 192.168.178.97 not responding.'),
                    subprocess.CompletedProcess([], 0, '{"phase":"restored"}', '')])

    def remote(*args, **kwargs):
        calls.append(args[0])
        return next(results)

    monkeypatch.setattr(vm, 'run_script', remote)
    monkeypatch.setattr(day.time, 'sleep', lambda seconds: None)
    assert day.restore_until_finished('same-journal', folder=tmp_path)['phase'] == 'restored'
    assert len(calls) == 2 and all('same-journal/guard.py' in value and "'restore'" in value for value in calls)
