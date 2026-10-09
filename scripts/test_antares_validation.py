"""Run all original Antares gates against the separately committed repair candidate."""

import json
import subprocess
from contextlib import closing

from test_support import ROOT, api, evidence, start, wait

with closing(api()) as client:
    pipeline = next(p for p in client.get("/api/pipelines").json() if p["id"] == "antares-ci")
    original = pipeline["spec"]
    if pipeline["enabled"] or original["repository"] not in {
        "/sources/antares",
        "/sources/antares-validation",
    }:
        raise ValueError("Expected the paused isolated Antares test catalog")
    candidate = {**original, "repository": "/sources/antares-validation", "ref": "leroy-validation"}
    commit = subprocess.check_output(
        ["git", "-C", str(ROOT / ".sources/antares-validation"), "rev-parse", "HEAD"], text=True
    ).strip()
    client.put("/api/pipelines/antares-ci", json=candidate).raise_for_status()
    try:
        run_id = start(client, "antares-ci", commit=commit)
        print("antares-ci", run_id, "candidate", commit, flush=True)
        run = wait(client, run_id, timeout=29000)
        evidence(client, run_id)
        result = {
            "run": run_id,
            "commit": commit,
            "repository": candidate["repository"],
            "status": run["status"],
        }
        (ROOT / "test-results/antares-validation.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        print(json.dumps(result), flush=True)
    finally:
        client.put("/api/pipelines/antares-ci", json=original).raise_for_status()
    raise SystemExit(0 if run["status"] == "succeeded" else 1)
