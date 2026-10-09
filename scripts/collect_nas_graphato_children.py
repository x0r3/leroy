"""Collect the actual child runs created by the original Graphato CI comparison."""

import argparse
import json
import subprocess
import sys
from contextlib import closing

from compare_nas_antares import client
from nas_candidate_paths import comparison_source
from nas_ssh import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate")
    args = parser.parse_args()
    _, root_folder = comparison_source("graphato-ci", args.candidate)
    aligned = root_folder.parent
    pair = json.loads((aligned / "graphato-ci/pair.json").read_text())
    found = {}
    with closing(client()) as api:

        def visit(run_id):
            response = api.get("/api/runs/" + run_id)
            response.raise_for_status()
            run = response.json()
            assert run["commit"] == pair["commit"]
            assert run["status"] in ("succeeded", "failed"), "Wait for all actual child runs"
            found[run["pipeline_id"]] = run
            for child in run["children"]:
                assert child["parent_id"] == run_id
                visit(child["id"])

        visit(pair["leroy_run"])
    assert set(found) == {
        "graphato-ci",
        "graphato-release-acceptance",
        "graphato-postdeploy-web",
        "graphato-postdeploy-quality",
    }
    for name, run in found.items():
        path = aligned / name / "pair.json"
        state = json.loads(path.read_text())
        assert state["commit"] == run["commit"]
        assert not state.get("leroy_run") or state["leroy_run"] == run["id"]
        assert all(run["parameters"][k] == v for k, v in state["parameters"].items())
        state["leroy_run"] = run["id"]
        state["leroy_status"] = run["status"]
        state["leroy_parent_id"] = run["parent_id"]
        path.write_text(json.dumps(state, indent=2) + "\n")
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/compare_nas_job.py"),
                name,
                "leroy",
                *(["--candidate", args.candidate] if args.candidate else []),
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
