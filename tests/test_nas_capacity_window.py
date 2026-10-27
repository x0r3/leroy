"""A closed maintenance approval cannot authorize another NAS service pause."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_nas_capacity_window as window  # noqa: E402


def test_run_requires_new_approval_before_any_nas_contact(monkeypatch, tmp_path):
    monkeypatch.setattr(window, 'PLAN', tmp_path)
    monkeypatch.setattr(window.vm, 'state', lambda: pytest.fail('No NAS contact without new approval'))
    with pytest.raises(AssertionError, match='new explicit approval'):
        window.run()
    (tmp_path / 'approval.json').write_text(json.dumps({'user_approved': True,
        'explicit_user_request': 'Previous two four-hour windows', 'maximum_window_seconds': 14400}))
    with pytest.raises((AssertionError, KeyError)):
        window.run()


def test_changed_source_invalidates_an_approved_plan(monkeypatch, tmp_path):
    monkeypatch.setattr(window, 'PLAN', tmp_path)
    plan = window.proposed_plan()
    approval = {**plan, 'user_approved': True, 'explicit_user_request': 'One new one-hour capacity window'}
    (tmp_path / 'approval.json').write_text(json.dumps(approval))
    assert window.require_approval()['user_approved']
    changed = {**plan, 'script_sha256': {**plan['script_sha256'], 'scripts/probe_nas_vm_capacity.py': '0' * 64}}
    monkeypatch.setattr(window, 'proposed_plan', lambda: changed)
    with pytest.raises(AssertionError, match='source changed'):
        window.require_approval()
