"""Run the preserved Graphato candidate afresh after its VM network correction."""

import argparse
import json
import subprocess
import sys
import time
from contextlib import closing

from compare_nas_antares import client
from nas_candidate_paths import comparison_source
from nas_ssh import ROOT
from prepare_nas_graphato_network_retry import ATTEMPT, CANDIDATE


def phase(script, *args):
    subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), *args], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true", help="Observe the existing retry without restarting jobs")
    args = parser.parse_args()
    _, ci = comparison_source("graphato-ci", CANDIDATE)
    previous = json.loads((ci / "pair.json").read_text())
    assert previous["vm_restore_attempt"] == ATTEMPT
    if args.resume:
        assert previous.get("leroy_run"), "No existing retry to observe"
        with closing(client()) as api:
            response = api.get("/api/runs/" + previous["leroy_run"])
            response.raise_for_status()
            run = response.json()
            assert run["commit"] == CANDIDATE and run["pipeline_id"] == "graphato-ci"
            assert run["parent_id"] is None
        finish(CANDIDATE, ci)
        return
    assert not previous.get("leroy_run"), "Use --resume to observe the existing retry"
    with closing(client()) as api:
        deadline = time.monotonic() + 3600
        while time.monotonic() < deadline:
            rows = []
            for status in ("running", "waiting", "queued"):
                response = api.get("/api/runs", params={"status": status})
                response.raise_for_status()
                rows.extend(response.json())
            assert all(row["id"] == "bc29298b409c4954b6ee7e41cdbf5cd2" for row in rows)
            if not rows:
                break
            time.sleep(20)
        else:
            raise TimeoutError("Existing Antares comparison still active; no Graphato job started")
        phase("compare_nas_job.py", "graphato-bootstrap-host", "start-leroy", "--candidate", CANDIDATE)
        pair = json.loads((ci.parent / "graphato-bootstrap-host/pair.json").read_text())
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            response = api.get("/api/runs/" + pair["leroy_run"])
            response.raise_for_status()
            run = response.json()
            if run["status"] not in ("queued", "running", "waiting"):
                break
            time.sleep(10)
        else:
            raise TimeoutError("Bootstrap still active; no CI run started")
        phase("compare_nas_job.py", "graphato-bootstrap-host", "leroy", "--candidate", CANDIDATE)
        assert run["status"] == "succeeded"
    phase("compare_nas_job.py", "graphato-ci", "start-leroy", "--candidate", CANDIDATE)
    finish(CANDIDATE, ci)


def finish(candidate, ci):
    phase("watch_nas_graphato_leroy.py", "--candidate", candidate)
    phase("nas_graphato_release_state.py", "leroy", "--candidate", candidate, "--via-leroy")
    phase("compare_nas_graphato.py", "--candidate", candidate)
    run_id = json.loads((ci / "pair.json").read_text())["leroy_run"]
    subprocess.run(
        ["node", str(ROOT / "scripts/verify_nas_graphato_candidate_ui.cjs"), run_id, candidate],
        check=True,
    )
    print("Fresh Graphato comparison and UI assertions complete; manual screenshot review remains.")


if __name__ == "__main__":
    main()
