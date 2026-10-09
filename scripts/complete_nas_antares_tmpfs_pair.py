"""Finish the explicit paired comparison after Jenkins; preserve failed gates."""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

from nas_followup_support import inner
from nas_ssh import ROOT
from verify_nas_antares_candidate import plain, test_counts

CANDIDATE = "8607cfd438c7645012bf0482a5da83acb122d6dd"


def browser_summary(text):
    counts = {name: int(number) for number, name in re.findall(
        r"^\s*(\d+) (passed|skipped|flaky|failed)\b", plain(text), re.MULTILINE,
    )}
    complete = counts.get("skipped") == 3 and sum(
        counts.get(name, 0) for name in ("passed", "flaky", "failed")
    ) == 26
    return {"complete": complete, **counts}


def observed_test_results(text):
    """Retain actual partial Vitest summaries when an earlier gate fails."""
    rows = []
    for summary, total in re.findall(r"^\s*Tests\s+(.+?)\s+\((\d+)\)\s*$", plain(text), re.MULTILINE):
        counts = {status: int(number) for number, status in re.findall(r"(\d+) (passed|failed|skipped)", summary)}
        rows.append({"total": int(total), **counts})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", default=CANDIDATE)
    parser.add_argument("--attempt", default="tmpfs-comparison",
                        help="Recorded retry name; an empty value selects the first comparison")
    parser.add_argument("--checkout", default=str(ROOT / ".sources/antares-nas-validation"))
    parser.add_argument("--execution-pool", help="Dedicated Linux worker evidence; controller stays on NAS")
    args = parser.parse_args()
    assert re.fullmatch(r"[a-f0-9]{40}", args.candidate)
    assert not args.attempt or re.fullmatch(r"[a-z][a-z0-9-]{0,23}", args.attempt)
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / args.candidate
    marker = folder / "tmpfs-complete-pair.json"
    assert not marker.exists(), "No implicit paired comparison rerun"
    deadline = time.monotonic() + 3600
    print("Waiting for the actual Jenkins result and restored stopped test Jenkins.", flush=True)
    while time.monotonic() < deadline:
        path = folder / "comparison.json"
        if path.exists():
            state = json.loads(path.read_text())
            assert state["commit"] == args.candidate and state.get("comparison_attempt", "") == args.attempt
            if state.get("jenkins", {}).get("result") and not state["jenkins"]["building"]:
                assert state["jenkins_restored"]["stopped"]
                assert state["temporary_storage_policy"]["candidate"] == args.candidate
                assert state["production_jobs_unchanged"], "Do not interpret a competing production build as quiet-host parity"
                break
        time.sleep(20)
    else:
        raise TimeoutError("Jenkins comparison not complete; no competing Leroy run started")
    if args.execution_pool:
        from setup_nas_linux_pool import nested
        pool = json.loads((ROOT / args.execution_pool).read_text())
        assert pool == state["execution_pool"]
        info = json.loads(nested("inspect", "jenkins-parity", text=True).stdout)[0]
        assert info["Id"] == pool["jenkins_id"] and not info["State"]["Running"]
    else:
        assert json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}")) is False
    if "No space left on device" in (folder / "jenkins-console.log").read_text(encoding="utf-8"):
        marker.write_text(json.dumps({
            "candidate": args.candidate, "jenkins_build": state["jenkins"]["number"],
            "jenkins_result": state["jenkins"]["result"], "leroy_pipeline_started": False,
            "reason": "Correct the shared database capacity before repeating the workload",
            "workload_success_both": False, "production_cutover": False,
        }, indent=2) + "\n")
        print("Database capacity failure retained; no automatic Leroy repetition.", flush=True)
        return
    print("Comparing the same source under Leroy; the actual failed Jenkins gates remain recorded.", flush=True)
    command = [sys.executable, "-X", "utf8", str(ROOT / "scripts/compare_nas_antares_candidate.py"),
               "leroy", "--via-leroy", "--checkout", args.checkout]
    if args.execution_pool:
        command.extend(["--execution-pool", args.execution_pool])
    if state["jenkins"]["result"] != "SUCCESS":
        command.append("--compare-failed-jenkins")
    result = subprocess.run(command, cwd=ROOT, check=False)
    state = json.loads((folder / "comparison.json").read_text())
    assert state.get("leroy_status") not in (None, "running", "queued", "waiting")
    assert result.returncode in (0, 1), "Unexpected collector interruption"
    assert state["leroy_production_jobs_unchanged"]
    if state["execution_success_both"]:
        subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/verify_nas_antares_candidate.py"),
                        "--candidate", args.candidate], cwd=ROOT, check=True)
        state = json.loads((folder / "comparison.json").read_text())
    run = json.loads((folder / "leroy-run.json").read_text())
    assert run["commit"] == args.candidate
    jenkins = plain((folder / "jenkins-console.log").read_text(encoding="utf-8"))
    leroy = plain((folder / "leroy-tests.log").read_text(encoding="utf-8"))
    if state["execution_success_both"]:
        counts = {"jenkins": test_counts(jenkins), "leroy": test_counts(leroy)}
        assert counts["jenkins"] == counts["leroy"]
    else:
        counts = {"jenkins": observed_test_results(jenkins), "leroy": observed_test_results(leroy)}
    browsers = {"jenkins": browser_summary(jenkins), "leroy": browser_summary((folder / "leroy-browsers.log").read_text(encoding="utf-8"))}
    subprocess.run(["node", str(ROOT / "scripts/verify_nas_antares_pair_ui.cjs"), run["id"], args.candidate], cwd=ROOT, check=True)
    record = {
        "at": datetime.now(timezone.utc).isoformat(), "candidate": args.candidate,
        "jenkins_build": state["jenkins"]["number"], "jenkins_result": state["jenkins"]["result"],
        "leroy_run": run["id"], "leroy_status": run["status"], "tests": counts, "browsers": browsers,
        "workload_success_both": state.get("workload_success_both", False),
        "same_test_counts": counts["jenkins"] == counts["leroy"], "original_assertions_and_timeouts_unchanged": True,
        "assertion_timeout_reference": "Same frozen candidate; original application unit/integration budgets differ",
        "temporary_storage_policy": "tmpfs-policy-applied.json", "production_modified": False,
        "production_cutover": False, "ui_manual_review_pending": True,
    }
    if args.execution_pool:
        record["execution_pool"] = state["execution_pool"]
        record["temporary_storage_policy"] = state["temporary_storage_policy"]
    marker.write_text(json.dumps(record, indent=2) + "\n")
    subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/summarize_nas_followup.py")], cwd=ROOT, check=True)
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
