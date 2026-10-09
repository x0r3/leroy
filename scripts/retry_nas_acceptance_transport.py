"""Repeat the original failed acceptance after changing only Leroys SSH transport."""

import argparse
import json
import re
import time
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from compare_nas_job import collect_artifacts
from nas_ssh import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", default="initial")
    attempt = parser.parse_args().attempt
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,40}", attempt):
        raise ValueError("Use an explicit, short attempt name")
    suffix = "" if attempt == "initial" else "-" + attempt
    folder = ROOT / ("test-results/nas-parity/followup/ssh-acceptance" + suffix)
    folder.mkdir(exist_ok=True)
    marker = folder / "run-id.json"
    old_id = "2d6bef89379740bbbc8ae9929ccd57ba"
    with closing(client()) as api:
        if marker.exists():
            run_id = json.loads(marker.read_text())["id"]
        else:
            response = api.get("/api/runs/" + old_id)
            response.raise_for_status()
            old = response.json()
            assert old["status"] == "failed" and old["commit"] == "48b741264f3b8353400649f6b05abf6a9c129233"
            response = api.post("/api/runs/" + old_id + "/retry")
            response.raise_for_status()
            run_id = response.json()["id"]
            marker.write_text(
                json.dumps({"id": run_id, "retry_of": old_id, "at": datetime.now(timezone.utc).isoformat()})
                + "\n"
            )
            print("Original acceptance transport retry:", run_id, flush=True)
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            response = api.get("/api/runs/" + run_id)
            response.raise_for_status()
            root = response.json()
            if root["status"] not in ("queued", "running", "waiting"):
                break
            time.sleep(10)
        else:
            raise TimeoutError(run_id)
        assert len(root["children"]) == 2
        rows = [root]
        for child in root["children"]:
            response = api.get("/api/runs/" + child["id"])
            response.raise_for_status()
            rows.append(response.json())
        report = {"run": run_id, "old_run": old_id, "application_patches_applied": False, "runs": {}}
        for run in rows:
            output = folder / run["pipeline_id"]
            output.mkdir(exist_ok=True)
            (output / "run.json").write_text(json.dumps(run, indent=2) + "\n")
            collect_artifacts(api, run, output)
            text = ""
            for step in run["steps"]:
                response = api.get(f"/api/runs/{run['id']}/logs/{step['id']}")
                response.raise_for_status()
                log = response.json()["text"]
                (output / (step["id"] + ".log")).write_text(log, encoding="utf-8")
                text += log
            assert run["status"] == "failed", "Original application gate must remain visible"
            assert "Connection timed out" not in text and "exit status 255" not in text
            assert "Connection refused" not in text and "could not be established" not in text
            if run is root:
                assert (
                    "Release acceptance incomplete; both full child suites and bound receipt are required"
                    in text
                )
                assert any(a["name"] == "release-status.json" for a in run["artifacts"])
            else:
                assert "CI deployment failed (ValueError)" in text
            report["runs"][run["pipeline_id"]] = {
                "id": run["id"],
                "status": run["status"],
                "no_transport_failure": True,
            }
        report["transport_regression_passed"] = True
        report["application_acceptance_passed"] = False
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
