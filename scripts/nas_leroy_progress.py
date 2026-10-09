"""Read a prepared Leroy comparison's current stage and bounded log tail."""

import argparse
import json
import sys
from contextlib import closing

from compare_nas_antares import client
from nas_ssh import ROOT


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pipeline")
    args = parser.parse_args()
    baseline = json.loads((ROOT / "test-results/nas-parity/baseline.json").read_text())
    assert args.pipeline in {p["pipeline"] for p in baseline["pipelines"]}
    folder = ROOT / "test-results/nas-parity/aligned" / args.pipeline
    state = json.loads((folder / "pair.json").read_text())
    with closing(client()) as api:
        response = api.get("/api/runs/" + state["leroy_run"])
        response.raise_for_status()
        run = response.json()
        print(run["id"], run["status"])
        print(json.dumps({s["id"]: s["status"] for s in run["steps"]}))
        active = next((s for s in run["steps"] if s["status"] == "running"), None)
        active = active or next((s for s in run["steps"] if s["status"] == "failed"), None)
        if active:
            response = api.get(
                f"/api/runs/{run['id']}/logs/{active['id']}",
                params={"offset": max(0, active["log_bytes"] - 2000)},
            )
            response.raise_for_status()
            print(response.json()["text"][-1800:])
        print("Children:", json.dumps(run["children"]))
    (folder / "leroy-progress.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
