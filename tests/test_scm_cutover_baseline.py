"""The handoff cannot hide missing work or fabricate successful execution history."""

import importlib
from pathlib import Path

import pytest
from sqlalchemy import func, select
from test_postgres import database  # noqa: F401

from leroy.db import Event, PipelineRow, Run
from leroy.engine import enqueue, finish
from leroy.schema import Pipeline, Step


@pytest.fixture
def baseline(database, monkeypatch):  # noqa: F811
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    tool = importlib.import_module("prepare_scm_baseline")
    _, sessions = database
    spec = Pipeline(id="handoff", name="handoff", repository="https://example.invalid/repo.git",
                    poll_seconds=120, steps=[Step(id="work", name="work", command=["true"])])
    with sessions.begin() as db:
        row = PipelineRow(id=spec.id, spec=spec.model_dump(), enabled=False)
        db.add(row)
        db.flush()
        run = enqueue(db, row, {}, commit="a" * 40)
        finish(db, run, "succeeded")
    return tool, sessions


def test_preview_does_not_change_polling_or_history(baseline):
    tool, sessions = baseline
    with sessions.begin() as db:
        before = db.scalar(select(func.count()).select_from(Event))
        result = tool.prepare_baseline(db, "handoff", "a" * 40)
        assert not result["applied"] and not result["changed"]
        assert db.get(PipelineRow, "handoff").last_revision is None
        assert db.scalar(select(func.count()).select_from(Event)) == before
        assert db.scalar(select(func.count()).select_from(Run)) == 1


def test_apply_is_idempotent_and_leaves_trigger_disabled(baseline):
    tool, sessions = baseline
    with sessions.begin() as db:
        assert tool.prepare_baseline(db, "handoff", "a" * 40, apply=True)["changed"]
    with sessions.begin() as db:
        assert not tool.prepare_baseline(db, "handoff", "a" * 40, apply=True)["changed"]
        row = db.get(PipelineRow, "handoff")
        assert row.last_revision == "a" * 40 and not row.enabled
        assert db.scalar(select(func.count()).select_from(Run)) == 1
        assert db.scalar(select(func.count()).select_from(Event).where(Event.kind == "scm.baseline.prepared")) == 1


def test_recorded_success_with_invalid_revision_cannot_seed_polling(baseline):
    tool, sessions = baseline
    malformed = "b" * 43
    with sessions.begin() as db:
        finish(db, enqueue(db, db.get(PipelineRow, "handoff"), {}, commit=malformed), "succeeded")
    with sessions.begin() as db:
        with pytest.raises(ValueError, match="exact Git commit"):
            tool.prepare_baseline(db, "handoff", malformed, apply=True)
        assert db.get(PipelineRow, "handoff").last_revision is None
        assert db.scalar(select(func.count()).select_from(Event).where(Event.kind == "scm.baseline.prepared")) == 0


def test_verified_sha256_git_revision_can_seed_polling(baseline):
    tool, sessions = baseline
    commit = "b" * 64
    with sessions.begin() as db:
        finish(db, enqueue(db, db.get(PipelineRow, "handoff"), {}, commit=commit), "succeeded")
    with sessions.begin() as db:
        assert tool.prepare_baseline(db, "handoff", commit, apply=True)["changed"]
        assert db.get(PipelineRow, "handoff").last_revision == commit


@pytest.mark.parametrize("scenario", ["enabled", "active", "unverified", "newer_failed", "not_scm"])
def test_invalid_handoff_cannot_suppress_work(baseline, scenario):
    tool, sessions = baseline
    with sessions.begin() as db:
        row = db.get(PipelineRow, "handoff")
        if scenario == "enabled":
            row.enabled = True
        elif scenario == "active":
            enqueue(db, row, {}, commit="b" * 40)
        elif scenario == "newer_failed":
            finish(db, enqueue(db, row, {}, commit="b" * 40), "failed")
        elif scenario == "not_scm":
            row.spec = {**row.spec, "poll_seconds": 0}
    with sessions.begin() as db:
        with pytest.raises(ValueError):
            tool.prepare_baseline(db, "handoff", "b" * 40 if scenario in {"unverified", "newer_failed"} else "a" * 40, apply=True)
        assert db.get(PipelineRow, "handoff").last_revision is None
