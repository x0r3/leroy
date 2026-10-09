"""Transactional execution state. No subprocesses or network calls inside transactions."""

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import aliased

from .db import Event, Run, RunnerRow, StepRow, now
from .schema import TERMINAL, Pipeline


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def event(db, run_id, kind, data=None, step_id=None):
    db.add(Event(run_id=run_id, kind=kind, data=data or {}, step_id=step_id))


def serialise(obj):
    result = {}
    for col in obj.__table__.columns:
        if col.name in {"token_hash", "password_hash"}:
            continue
        value = getattr(obj, col.name)
        result[col.name] = value.isoformat() if hasattr(value, "isoformat") else value
    return result


def enqueue(
    db,
    row,
    parameters,
    *,
    actor="system",
    trigger="manual",
    commit=None,
    parent_id=None,
    retry_of=None,
    dedupe_key=None,
    snapshot=None,
):
    spec = Pipeline.model_validate(snapshot or row.spec)
    bound = spec.bind(parameters)
    db.execute(text("SELECT pg_advisory_xact_lock(7046101)"))
    if dedupe_key:
        existing = db.scalar(select(Run).where(Run.dedupe_key == dedupe_key))
        if existing:
            return existing
    if spec.concurrency == "replace":
        for old in db.scalars(select(Run).where(Run.pipeline_id == row.id, Run.status.not_in(TERMINAL))):
            request_cancel(db, old, "Superseded by a newer run")
    run = Run(
        pipeline_id=row.id,
        snapshot=spec.model_dump(),
        parameters=bound,
        actor=actor,
        trigger=trigger,
        commit=commit,
        parent_id=parent_id,
        retry_of=retry_of,
        dedupe_key=dedupe_key,
        resource=spec.resource,
    )
    db.add(run)
    db.flush()
    for i, step in enumerate(spec.steps):
        db.add(StepRow(run_id=run.id, id=step.id, name=step.name, position=i, needs=step.needs))
    event(db, run.id, "run.queued", {"trigger": trigger, "actor": actor, "retry_of": retry_of})
    return run


def request_cancel(db, run, reason):
    # Same lock order as claiming/child creation; refresh a potentially stale caller's row.
    db.execute(text("SELECT pg_advisory_xact_lock(7046101)"))
    run = db.scalar(
        select(Run).where(Run.id == run.id).with_for_update().execution_options(populate_existing=True)
    )
    if run.status in TERMINAL:
        return
    if not run.cancel_requested:
        run.cancel_requested = True
        run.reason = reason
        event(db, run.id, "run.cancel_requested", {"reason": reason})
    if run.status == "queued":
        finish(db, run, "cancelled", reason)
    cancel_children(db, run, "Parent run cancelled: " + run.reason)


def cancel_children(db, run, reason):
    for child in db.scalars(select(Run).where(Run.parent_id == run.id, Run.status.not_in(TERMINAL))):
        request_cancel(db, child, reason)


def finish(db, run, status, reason=""):
    run.status, run.reason, run.finished_at = status, reason, now()
    run.lease_until = None
    run.token_hash = None
    for step in db.scalars(select(StepRow).where(StepRow.run_id == run.id)):
        if step.status not in TERMINAL:
            step.status = "skipped" if step.status == "pending" else status
            step.reason = reason or "Run ended before this step could complete"
            step.finished_at = now()
    event(db, run.id, "run." + status, {"reason": reason})


def validate_child_call(db, parent, step, child_spec):
    """Reject recursion and resource waits that cannot make progress."""
    current, waiting = parent, bool(step.get("options", {}).get("wait"))
    while current is not None:
        if current.pipeline_id == child_spec.id:
            raise ValueError(f"Child pipeline cycle: {child_spec.id} is already an ancestor")
        if (
            waiting
            and child_spec.resource
            and current.resource == child_spec.resource
            and current.status in ("running", "waiting")
        ):
            raise ValueError(
                f"Child resource {child_spec.resource} is held by waiting ancestor {current.pipeline_id}"
            )
        ancestor = db.get(Run, current.parent_id) if current.parent_id else None
        if ancestor is not None:
            # A fire-and-forget edge breaks the wait chain: its parent can finish
            # independently and release its resource. Preserve this valid case.
            waiting = waiting and any(
                current.dedupe_key == f"child:{ancestor.id}:{item['id']}"
                and item.get("options", {}).get("wait")
                for item in ancestor.snapshot["steps"]
                if item["action"] == "child"
            )
        current = ancestor


def claim(db, runner_id, profiles, capacity):
    db.execute(text("SELECT pg_advisory_xact_lock(7046101)"))
    runner = db.get(RunnerRow, runner_id)
    if runner is None:
        runner = RunnerRow(id=runner_id)
        db.add(runner)
    runner.last_seen, runner.profiles, runner.capacity = now(), profiles, capacity
    active = db.scalar(
        select(func.count()).select_from(Run).where(Run.runner == runner_id, Run.status == "running")
    )
    if active >= capacity:
        return None
    other = aliased(Run)
    same_pipeline = (
        select(other.id)
        .where(other.status.in_(("running", "waiting")), other.pipeline_id == Run.pipeline_id)
        .exists()
    )
    same_resource = (
        select(other.id)
        .where(other.status.in_(("running", "waiting")), other.resource == Run.resource)
        .exists()
    )
    rows = db.scalars(
        select(Run)
        .where(
            Run.status == "queued",
            Run.snapshot["profile"].astext.in_(profiles),
            or_(Run.snapshot["concurrency"].astext == "parallel", ~same_pipeline),
            or_(Run.resource.is_(None), ~same_resource),
        )
        .order_by(Run.number)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    for run in rows:
        token = secrets.token_urlsafe(40)
        run.token_hash, run.runner = digest(token), runner_id
        run.status, run.started_at = "running", now()
        run.lease_until = now() + timedelta(seconds=90)
        event(db, run.id, "run.started", {"runner": runner_id})
        result = serialise(run)
        previous = db.scalar(
            select(Run)
            .where(Run.pipeline_id == run.pipeline_id, Run.status == "succeeded", Run.commit.is_not(None))
            .order_by(Run.number.desc())
            .limit(1)
        )
        result["previous_successful_commit"] = previous.commit if previous else None
        result["token"] = token
        return result
    return None


def reconcile(db):
    db.execute(text("SELECT pg_advisory_xact_lock(7046101)"))
    for run in db.scalars(
        select(Run).where(Run.status.in_(("running", "waiting"))).with_for_update(skip_locked=True)
    ):
        if run.lease_until and run.lease_until < now():
            cancel_children(db, run, "Parent runner lease expired")
            finish(db, run, "interrupted", "Runner lease expired; external effects require reconciliation")
        elif run.started_at and (now() - run.started_at).total_seconds() > run.snapshot["timeout"]:
            request_cancel(db, run, "Pipeline timeout exceeded")
