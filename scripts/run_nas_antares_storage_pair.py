"""Run two bounded original-test diagnostics after the Graphato pair completes.

This one-off sequence varies only trace/video storage. It never retries failed
tests beyond their original Playwright retry, and never claims full CI acceptance.
"""

import argparse
import json
import re
import subprocess
import sys
import time

from nas_gitea_target import idle
from nas_ssh import ROOT


def read(path):
    return json.loads(path.read_text())


def phase(script, *args):
    print("Antares storage phase:", script, *args, flush=True)
    subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), *args],
                   cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--after-graphato", required=True)
    args = parser.parse_args()
    assert all(re.fullmatch("[a-f0-9]{40}", value) for value in (args.candidate, args.after_graphato))
    graphato = ROOT / "test-results/nas-parity/followup/candidates/graphato" / args.after_graphato
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / args.candidate
    assert read(folder / "staged.json")["commit"] == args.candidate
    report = folder / "trace-storage-pair.json"
    assert not report.exists(), "No implicit diagnostic rerun"
    print("Waiting for the complete Graphato pair; no concurrent NAS diagnostic.", flush=True)
    deadline = time.monotonic() + 9 * 3600
    while time.monotonic() < deadline:
        if (graphato / "complete-pair.json").exists():
            assert read(graphato / "complete-pair.json")["pipelines_successful"]
            assert read(graphato / "comparison.json")["workload_success_both"]
            break
        for name in ("jenkins-bootstrap-watch.json", "jenkins-release-watch.json"):
            path = graphato / name
            if path.exists():
                assert all(row.get("result") == "SUCCESS" for row in read(path)["builds"].values()), (
                    "Graphato failed; preserve evidence and inspect before continuing"
                )
        leroy_watch = graphato / "leroy-run-watch.json"
        if leroy_watch.exists():
            assert read(leroy_watch)["all_successful"], "Leroy Graphato failed; no Antares probe started"
        bootstrap = graphato / "graphato-bootstrap-host/pair.json"
        if bootstrap.exists() and read(bootstrap).get("leroy_status"):
            assert read(bootstrap)["leroy_status"] == "succeeded", "Leroy bootstrap failed"
        time.sleep(30)
    else:
        raise TimeoutError("Graphato still incomplete; no Antares diagnostic started")
    idle()
    ci = read(graphato / "graphato-ci/pair.json")["leroy_run"]
    assert re.fullmatch("[a-f0-9]{32}", ci)
    ui = ROOT / "test-results/nas-parity" / ("visual-graphato-" + args.after_graphato[:12]) / "report.json"
    if not ui.exists():
        print("Validating the actual completed Graphato hierarchy in headless desktop/mobile UI.", flush=True)
        subprocess.run(["node", str(ROOT / "scripts/verify_nas_graphato_candidate_ui.cjs"),
                        ci, args.after_graphato], cwd=ROOT, check=True)
    checked = read(ui)
    assert checked["passed"] and checked["commit"] == args.after_graphato and ci in checked["runs"]
    print("UI checks passed; manual visual review: " +
          str(checked.get("manual_visual_review", False)), flush=True)
    probes = []
    for attempt, ram in (("ram-trace-auth", True), ("disk-trace-auth", False)):
        marker = folder / ("focused-browsers-" + attempt + ".json")
        if not marker.exists():
            phase("probe_nas_antares_browsers.py", "--candidate", args.candidate,
                  "--attempt", attempt, "--test-file", "tests/e2e/game-auth.spec.ts",
                  "--project", "game-chromium", "--timeout-seconds", "480",
                  "--database-tmpfs", "--browser-tmpfs",
                  *(["--artifacts-in-tmpfs"] if ram else []))
        result = read(marker)
        assert result["commit"] == args.candidate and result["diagnostic_only"]
        assert result["database_tmpfs"] and result["browser_tmpfs"]
        assert result["artifacts_in_tmpfs"] is ram
        assert result["test_files"] == ["tests/e2e/game-auth.spec.ts"]
        assert result["projects"] == ["game-chromium"]
        assert result["helpers_removed"], "Finish the recorded diagnostic cleanup before continuing"
        phase("collect_nas_antares_browser_failures.py", "--candidate", args.candidate,
              "--attempt", attempt, "--result-directory", result["artifact_directory"],
              "--trace", "game-auth")
        probes.append({"evidence": marker.relative_to(ROOT).as_posix(), **result})
        assert result["production_build_unchanged"], "Production overlapped; do not infer a storage effect"
    record = {
        "candidate": args.candidate, "diagnostic_only": True,
        "full_ci_acceptance": False, "original_assertions_and_timeouts_unchanged": True,
        "scope": "Two focused probes varying trace/video output storage; not a repeated performance benchmark",
        "graphato_pair": args.after_graphato, "probes": probes,
    }
    report.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"diagnostic_only": True, "probes": [
        {key: row[key] for key in ("attempt", "passed", "duration_seconds", "production_build_unchanged")}
        for row in probes
    ]}), flush=True)


if __name__ == "__main__":
    main()
