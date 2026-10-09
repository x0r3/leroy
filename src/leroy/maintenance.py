"""Retention preserves complete parent/retry families and every active run."""

import logging
import re
import shutil
from datetime import timedelta

from sqlalchemy import delete, select, text

from .db import Artifact, FileDeletion, PipelineRow, Run, Session, lock_log_files, now
from .schema import TERMINAL


def retention_candidates(rows, limits, cutoff):
    protected, counts = set(), {}
    for row in sorted(rows, key=lambda r: r.number, reverse=True):
        count = counts.get(row.pipeline_id, 0)
        if count < limits.get(row.pipeline_id, 50) or row.status not in TERMINAL or row.created_at >= cutoff:
            protected.add(row.id)
        counts[row.pipeline_id] = count + 1
    # Keep the whole linked family so acceptance and retry history stays inspectable.
    changed = True
    while changed:
        before = len(protected)
        for row in rows:
            links = {row.id, row.parent_id, row.retry_of} - {None}
            if links & protected:
                protected.update(links)
        changed = len(protected) != before
    return [r.id for r in sorted(rows, key=lambda r: r.number, reverse=True) if r.id not in protected]


def retain(sessions, directory, min_age_days=7):
    with sessions.begin() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(7046101)"))
        db.execute(delete(Session).where(Session.expires < now()))
        rows = list(
            db.execute(
                select(
                    Run.id,
                    Run.number,
                    Run.pipeline_id,
                    Run.status,
                    Run.created_at,
                    Run.parent_id,
                    Run.retry_of,
                )
            )
        )
        limits = {p.id: p.spec.get("retention_runs", 50) for p in db.scalars(select(PipelineRow))}
        expired = retention_candidates(rows, limits, now() - timedelta(days=min_age_days))
        artifacts = list(db.scalars(select(Artifact.id).where(Artifact.run_id.in_(expired))))
        for kind, ids in (("artifacts", artifacts), ("logs", expired)):
            for id in ids:
                db.add(FileDeletion(kind=kind, id=id))
        # Descendants have newer sequence numbers; remove them before their ancestors.
        for id in expired:
            db.execute(delete(Run).where(Run.id == id, Run.status.in_(TERMINAL)))
    collect_files(sessions, directory)
    return len(expired)


def collect_files(sessions, directory):
    # Intent and DB removal commit together. Failed or interrupted I/O is retried
    # next time, including when the filesystem operation succeeded before a crash.
    with sessions() as db:
        pending = db.execute(select(FileDeletion.kind, FileDeletion.id)).all()
    for kind, id in pending:
        try:
            with sessions.begin() as db:
                item = db.scalar(
                    select(FileDeletion)
                    .where(FileDeletion.kind == kind, FileDeletion.id == id)
                    .with_for_update(skip_locked=True)
                )
                if item is None:
                    continue
                if item.upload_run_id:
                    run = db.get(Run, item.upload_run_id)
                    if run is not None and run.status not in TERMINAL:
                        continue
                if kind not in ("artifacts", "logs") or not re.fullmatch(r"[a-f0-9]{32}", id):
                    raise ValueError("Invalid file deletion target")
                if kind == "logs" and not lock_log_files(db, id, wait=False):
                    continue
                path = directory / kind / id
                if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                    raise ValueError("File deletion escaped data directory")
                if kind == "artifacts":
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    shutil.rmtree(path)
                db.delete(item)
        except (OSError, ValueError) as exc:
            logging.getLogger("leroy.retention").error(
                "File cleanup will be retried (%s)", type(exc).__name__
            )
