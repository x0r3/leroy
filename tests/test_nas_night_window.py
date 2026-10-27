"""An overnight extension must not reuse a closed capacity approval."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_nas_night_window as night  # noqa: E402


def test_night_requires_new_approval_before_preparation(monkeypatch, tmp_path):
    monkeypatch.setattr(night, 'PLAN', tmp_path)
    monkeypatch.setattr(night, 'prepare_on_nas', lambda *a, **kw: pytest.fail('No NAS access'))
    with pytest.raises(AssertionError, match='separate explicit overnight'):
        night.run()


def test_approval_binds_source_scope_and_absolute_morning_end(monkeypatch, tmp_path):
    monkeypatch.setattr(night, 'PLAN', tmp_path)
    plan = night.proposed_plan()
    approval = {**plan, 'user_approved': True, 'explicit_user_request': 'Die ganze Nacht'}
    path = tmp_path / 'approval.json'
    path.write_text(json.dumps(approval))
    assert night.require_approval()['absolute_deadline_epoch'] == night.DEADLINE
    for change in [{'absolute_deadline_epoch': night.DEADLINE + 7200},
                   {'script_sha256': {}}, {'comparison_rounds': ['an-old-window']}]:
        path.write_text(json.dumps({**approval, **change}))
        with pytest.raises(AssertionError, match='scope or source changed'):
            night.require_approval()


@pytest.mark.parametrize('progress', [
    {'id': 'a' * 32, 'status': 'running', 'steps': {'check': 'running'}},
    {'runs': {'release': {'id': 'a' * 32, 'status': 'running'},
              'quality': {'id': 'b' * 32, 'status': 'queued'}}},
])
def test_recovery_registers_single_original_job_and_nested_release_runs(monkeypatch, tmp_path, progress):
    (tmp_path / 'leroy-start.json').write_text(json.dumps({'id': 'a' * 32}))
    (tmp_path / 'leroy-progress.json').write_text(json.dumps(progress))
    calls = []

    def action(remote, name, run=None):
        calls.append((name, run))
        return {'runs': []}

    monkeypatch.setattr(night, 'action', action)
    night.register_runs('own-window', tmp_path)
    assert {run for name, run in calls if name == 'register'} == (
        {'a' * 32, 'b' * 32} if 'runs' in progress else {'a' * 32})
