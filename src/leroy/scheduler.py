import logging
import subprocess
import time
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy import select, text

from .db import PipelineRow, now
from .engine import enqueue, reconcile
from .git_auth import git_environment
from .maintenance import retain

log = logging.getLogger("leroy.scheduler")


def scm_credentials(config, pipeline_id):
    # Git needs file paths for SSH material, but values for HTTP authentication.
    return {
        name: str(Path(path))
        if name in ("GIT_SSH_KEY_FILE", "GIT_KNOWN_HOSTS")
        else Path(path).read_text(encoding="utf-8").strip()
        for name, path in config.get("scm_credentials", {}).get(pipeline_id, {}).items()
    }


def next_due(spec, after):
    if spec.get("schedule"):
        return croniter(
            spec["schedule"], after.astimezone(ZoneInfo(spec["timezone"])), hash_id=spec["id"]
        ).get_next(type(after))
    return after + timedelta(seconds=spec.get("poll_seconds") or 60)


def scheduler(sessions, settings, stop):
    next_retention = time.monotonic() + 3600
    while not stop.is_set():
        try:
            if time.monotonic() >= next_retention:
                retain(sessions, settings.data, settings.config.get("retention_min_age_days", 7))
                next_retention = time.monotonic() + 3600
            with sessions.begin() as db:
                reconcile(db)
                due = []
                for row in db.scalars(
                    select(PipelineRow).where(PipelineRow.enabled.is_(True)).with_for_update(skip_locked=True)
                ):
                    if not (row.spec.get("schedule") or row.spec.get("poll_seconds")):
                        continue
                    if row.next_trigger is None:
                        try:
                            row.next_trigger = next_due(row.spec, now())
                        except (ValueError, KeyError) as exc:
                            log.error("Pipeline %s has an invalid schedule (%s)", row.id, type(exc).__name__)
                    elif row.next_trigger <= now():
                        due.append((row.id, row.spec, row.next_trigger))
            for id, spec, scheduled_at in due:
                try:
                    commit = None
                    if spec.get("poll_seconds"):
                        credentials = scm_credentials(settings.config, id)
                        with git_environment(credentials) as env:
                            result = subprocess.run(
                                ["git", "ls-remote", "--", spec["repository"], "refs/heads/" + spec["ref"]],
                                capture_output=True,
                                text=True,
                                timeout=30,
                                check=True,
                                env=env,
                            )
                        if not result.stdout.strip():
                            raise ValueError("SCM branch not found")
                        commit = result.stdout.split()[0]
                    with sessions.begin() as db:
                        db.execute(text("SELECT pg_advisory_xact_lock(7046101)"))
                        row = db.scalar(select(PipelineRow).where(PipelineRow.id == id).with_for_update())
                        if not row or not row.enabled or row.next_trigger != scheduled_at:
                            continue
                        # Advance and enqueue atomically. A crash during SCM lookup leaves the
                        # occurrence due; a competing scheduler cannot enqueue it twice.
                        # Coalesce missed schedules instead of replaying mutations after downtime.
                        row.next_trigger = next_due(row.spec, now())
                        if commit and commit == row.last_revision:
                            continue
                        enqueue(
                            db,
                            row,
                            {},
                            trigger="scm" if commit else "schedule",
                            commit=commit,
                            dedupe_key=f"{id}:{commit or scheduled_at.isoformat()}",
                        )
                        if commit:
                            row.last_revision = commit
                except Exception as exc:
                    log.error("Pipeline %s could not be scheduled (%s)", id, type(exc).__name__)
        except Exception as exc:
            # Never log credential-bearing command arguments or response bodies.
            log.error("Scheduler operation failed (%s)", type(exc).__name__)
        stop.wait(2)
