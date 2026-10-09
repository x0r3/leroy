"""Seal actual CI, artifact, UI and cleanup evidence without starting another run."""

import hashlib
import json
import os
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from compare_nas_antares import client
from nas_followup_support import production_jobs
from nas_ssh import ROOT
from setup_nas_linux_pool import COMMIT, EVIDENCE, PARENT, docker, nested


def main():
    destination = EVIDENCE / "complete-pair.json"
    assert not destination.exists(), "Retain the original final verification"
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / COMMIT
    comparison = json.loads((folder / "comparison.json").read_text())
    run = json.loads((folder / "leroy-run.json").read_text())
    pool = json.loads((EVIDENCE / "pool.json").read_text())
    assert comparison["execution_pool"] == pool and comparison["commit"] == COMMIT
    assert comparison["workload_success_both"] and comparison["complete_matching_gates"]
    assert comparison["leroy_run"] == run["id"] and comparison["jenkins"]["result"] == "SUCCESS"
    assert run["commit"] == COMMIT and run["status"] == "succeeded"
    assert len(run["steps"]) == 9 and all(step["status"] == "succeeded" for step in run["steps"])
    parent = json.loads(docker("inspect", PARENT, text=True).stdout)[0]
    assert parent["Id"] == pool["parent_id"] and parent["State"]["Running"]
    assert parent["Config"]["Labels"]["io.leroy.nas-linux-pool"] == "true"
    assert parent["HostConfig"]["Memory"] == parent["HostConfig"]["MemorySwap"] == 8 * 1024**3
    assert not parent["State"]["OOMKilled"]
    remaining = nested("ps", "-a", "--filter", "label=io.leroy.run=" + run["id"],
                       "--format", "{{.ID}} {{.Names}}", text=True).stdout.strip()
    volumes = nested("volume", "ls", "--format", "{{.Name}}", text=True).stdout.splitlines()
    assert not remaining and "leroy-" + run["id"] + "-work" not in volumes
    jenkins = json.loads(nested("inspect", "jenkins-parity", text=True).stdout)[0]
    assert jenkins["Id"] == pool["jenkins_id"] and not jenkins["State"]["Running"]
    assert jenkins["HostConfig"]["Memory"] == 2 * 1024**3
    assert jenkins["HostConfig"]["NanoCpus"] == 2_000_000_000
    events = [json.loads(line) for line in nested(
        "events", "--since", run["started_at"], "--until", run["finished_at"],
        "--filter", "event=oom", "--format", "{{json .}}", text=True,
    ).stdout.splitlines() if line.strip()]
    assert not events, "Retain an OOM event instead of claiming a clean completed workload"
    archive = folder / "leroy-artifacts"
    artifacts = []
    for item in run["artifacts"]:
        name = PurePosixPath(item["name"])
        step = PurePosixPath(item["step_id"])
        assert len(step.parts) == 1 and step.name not in (".", "..")
        assert not name.is_absolute() and ".." not in name.parts
        path = archive.joinpath(step.name, *name.parts).resolve()
        assert path.is_relative_to(archive.resolve())
        if os.name == "nt":
            value = str(path)
            path = Path("\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value)
        assert path.stat().st_size == item["size"]
        with path.open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == item["sha256"]
        artifacts.append({key: item[key] for key in ("id", "step_id", "name", "size", "sha256")})
    visual = ROOT / "test-results/nas-parity" / ("visual-antares-" + run["id"]) / "report.json"
    ui = json.loads(visual.read_text())
    assert ui["passed"] and ui["manual_visual_review"] and not ui["errors"]
    assert ui["run"] == run["id"] and ui["commit"] == COMMIT and len(ui["screenshots"]) == 6
    with closing(client()) as api:
        response = api.get("/health/ready")
        response.raise_for_status()
        for status in ("running", "queued", "waiting"):
            response = api.get("/api/runs", params={"status": status})
            response.raise_for_status()
            assert not response.json()
        response = api.get("/api/pipelines")
        response.raise_for_status()
        assert not any(pipeline["enabled"] for pipeline in response.json())
    production = production_jobs()
    assert len(production["jobs"]) == 13
    assert production["jobs"] == comparison["production_jobs_after"]["jobs"]
    assert production["jobs"] == comparison["leroy_production_jobs_after"]["jobs"]
    record = {
        "at": datetime.now(timezone.utc).isoformat(), "candidate": COMMIT,
        "jenkins_build": comparison["jenkins"]["number"], "leroy_run": run["id"],
        "workload_success_both": True, "complete_matching_gates": True,
        "execution_host": pool["execution_host"], "controller": pool["controller"],
        "job_and_nested_helpers_removed": True, "job_work_volume_removed": True,
        "jenkins_stopped_and_budget_restored": True, "controller_ready": True,
        "automatic_triggers_disabled": True, "production_jobs_unchanged": True,
        "production_jobs": production["jobs"], "leroy_oom_events": events,
        "artifacts_verified": artifacts, "artifact_count": len(artifacts),
        "ui_evidence": visual.relative_to(ROOT).as_posix(), "manual_visual_review": True,
        "full_ci_acceptance": True, "production_replacement_ready": False,
        "production_modified": False, "production_cutover": False,
        "scope": "Frozen candidate CI on a dedicated Linux pool; no NAS-only capacity or production cutover acceptance",
        "passed": True,
    }
    destination.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({key: record[key] for key in ("candidate", "leroy_run", "artifact_count", "passed")}))


if __name__ == "__main__":
    main()
