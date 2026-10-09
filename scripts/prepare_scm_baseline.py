"""Prepare SCM polling from a genuinely successful Leroy run; dry-run by default.

Run inside the controller as its trusted host administrator. This command never
creates a successful run, starts a job, enables a pipeline, or changes a target.
"""

import argparse
import json
import re

from sqlalchemy import select, text

from leroy.db import PipelineRow, Run
from leroy.engine import event


def prepare_baseline(db, pipeline_id, commit, *, apply=False):
    if not re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", commit):
        raise ValueError("The baseline must be an exact Git commit")
    db.execute(text("SELECT pg_advisory_xact_lock(7046101)"))
    pipeline = db.scalar(select(PipelineRow).where(PipelineRow.id == pipeline_id).with_for_update())
    if pipeline is None or pipeline.enabled:
        raise ValueError("The selected pipeline must exist and remain disabled")
    if not pipeline.spec.get("poll_seconds") or not pipeline.spec.get("repository"):
        raise ValueError("The selected pipeline must use SCM polling")
    active = db.scalar(select(Run.id).where(Run.status.in_({"queued", "running", "waiting"})).limit(1))
    if active:
        raise ValueError("Complete all active runs before preparing the cutover baseline")
    successful = db.scalar(select(Run).where(Run.pipeline_id == pipeline_id, Run.status == "succeeded",
                                            Run.commit.is_not(None)).order_by(Run.number.desc()).limit(1))
    if successful is None or successful.commit != commit:
        raise ValueError("The baseline must match the latest actually successful Leroy run")
    changed = pipeline.last_revision != commit
    result = {"pipeline": pipeline_id, "commit": commit, "successful_run": successful.id,
              "previous_scm_revision": pipeline.last_revision, "applied": apply, "changed": changed and apply,
              "pipeline_remains_disabled": True, "run_created": False, "target_modified": False}
    if apply and changed:
        pipeline.last_revision = commit
        pipeline.next_trigger = None
        event(db, None, "scm.baseline.prepared", {"pipeline": pipeline_id, "commit": commit,
              "successful_run": successful.id, "actor": "trusted-host-administrator"})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pipeline")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--apply", action="store_true", help="Apply only after approving the production cutover")
    args = parser.parse_args()
    from leroy.config import Settings
    from leroy.db import connect

    engine, sessions = connect(Settings.load().database_url)
    try:
        with sessions.begin() as db:
            result = prepare_baseline(db, args.pipeline, args.commit, apply=args.apply)
        print(json.dumps(result))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
