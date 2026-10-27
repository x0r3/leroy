"""VM recovery identity must follow boot even without a new Leroy run ID."""

import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_nas_original_night_window as night  # noqa: E402


def simulate_stage(monkeypatch, tmp_path, case):
    polls = [0]
    captured_after_boot = []
    monkeypatch.setattr(night, 'DEADLINE', time.time() + 3600)
    monkeypatch.setattr(night, 'require_approval', lambda: None)
    monkeypatch.setattr(night, 'idle', lambda: None)
    monkeypatch.setattr(night, 'register_runs', lambda *args: None)
    monkeypatch.setattr(night.time, 'sleep', lambda seconds: None)

    def poll():
        polls[0] += 1
        return None if polls[0] <= 2 else 0

    def action(remote, operation):
        # The first poll can happen before the independently booted VM exists.
        if operation == 'register-vm' and polls[0] >= 2:
            captured_after_boot.append(True)
        return {'phase': 'paused', 'deadline': night.DEADLINE}

    monkeypatch.setattr(night, 'action', action)
    monkeypatch.setattr(night.subprocess, 'Popen', lambda *args, **kwargs:
                        SimpleNamespace(pid=123, returncode=0, poll=poll))
    night.stage(tmp_path, 'unused', 'full-release-jenkins', ['unused'], case=case)
    return captured_after_boot


@pytest.mark.parametrize('retained_leroy_marker', [False, True])
def test_jenkins_boot_refreshes_identity_without_new_leroy_run_ids(monkeypatch, tmp_path, retained_leroy_marker):
    case = tmp_path / 'case'
    case.mkdir()
    if retained_leroy_marker:
        (case / 'leroy-start.json').write_text('{"id":"retained-original-run"}')
    assert simulate_stage(monkeypatch, tmp_path, case)


def test_closed_disk_archive_never_registers_an_active_vm(monkeypatch, tmp_path):
    assert not simulate_stage(monkeypatch, tmp_path, None)
