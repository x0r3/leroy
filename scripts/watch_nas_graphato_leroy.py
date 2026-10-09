"""Observe the actual candidate run tree, then collect its completed evidence."""

import argparse
import json
import subprocess
import sys
import time
from contextlib import closing
from datetime import datetime, timezone

import httpx
from compare_nas_antares import client
from nas_candidate_paths import comparison_source
from nas_ssh import ROOT


def read_tree(api, run_id, candidate, expected):
    rows, seen = {}, set()

    def visit(identity, parent=None):
        assert identity not in seen
        seen.add(identity)
        response = api.get("/api/runs/" + identity)
        response.raise_for_status()
        run = response.json()
        assert run["commit"] == candidate and run["parent_id"] == parent
        assert run["pipeline_id"] in expected and run["pipeline_id"] not in rows
        rows[run["pipeline_id"]] = {
            "id": identity,
            "status": run["status"],
            "steps": {step["id"]: step["status"] for step in run["steps"]},
        }
        for child in run["children"]:
            visit(child["id"], identity)

    visit(run_id)
    return rows


def authenticated_tree(run_id, candidate, expected):
    # A comparison can outlive the admin session. Reopen the read-only observer
    # so client() verifies/renews its private session before each snapshot.
    for attempt in range(2):
        with closing(client()) as api:
            try:
                return read_tree(api, run_id, candidate, expected)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 401 or attempt:
                    raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args()
    _, folder = comparison_source("graphato-ci", args.candidate)
    pair = json.loads((folder / "pair.json").read_text())
    run_id = pair["leroy_run"]
    expected = {"graphato-ci", "graphato-release-acceptance", "graphato-postdeploy-web", "graphato-postdeploy-quality"}
    previous = None
    deadline = time.monotonic() + 9 * 3600
    while time.monotonic() < deadline:
        rows = authenticated_tree(run_id, args.candidate, expected)
        if rows != previous:
            print(json.dumps(rows), flush=True)
            with (folder.parent / "leroy-run-progress.jsonl").open("a") as output:
                output.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "runs": rows}) + "\n")
            previous = rows
        if not any(row["status"] in {"queued", "running", "waiting"} for row in rows.values()):
            break
        time.sleep(20)
    else:
        raise TimeoutError("Candidate observation expired; no run was cancelled")
    report = {
        "candidate": args.candidate,
        "runs": rows,
        "all_successful": set(rows) == expected and all(row["status"] == "succeeded" for row in rows.values()),
    }
    (folder.parent / "leroy-run-watch.json").write_text(json.dumps(report, indent=2) + "\n")
    if set(rows) == expected:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/collect_nas_graphato_children.py"), "--candidate", args.candidate],
            check=True,
        )
    else:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/compare_nas_job.py"), "graphato-ci", "leroy", "--candidate", args.candidate],
            check=True,
        )
    assert report["all_successful"], "Actual failures retained; inspect candidate run evidence"
    print("All four Leroy candidate runs completed successfully and their artifacts were collected.", flush=True)


if __name__ == "__main__":
    main()
