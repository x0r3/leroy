"""Compare one frozen production revision on fresh isolated targets; retain failures."""

import json
import subprocess
import sys
import time
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from nas_followup_support import inner, production_jobs
from nas_gitea_target import idle
from nas_ssh import ROOT
from stage_nas_production_graphato import COMMIT
from watch_nas_graphato_via_leroy import JENKINS_ID


def phase(name, *args, failed_result_allowed=False):
    print("Production source comparison:", name, *args, flush=True)
    result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / name), *args], cwd=ROOT)
    if result.returncode and not failed_result_allowed:
        raise RuntimeError("Comparison phase failed; retain its result: " + name)
    return result.returncode


def read(path):
    return json.loads(path.read_text())


def capture_preparation(base, engine):
    destination = base / (engine + "-vm-preparation.json")
    if not destination.exists():
        ready = read(ROOT / "test-results/nas-parity/vm-ready.json")
        assert ready["automatic_package_updates"]["background_upgrades_inactive"]
        assert not ready["application_installed"] and ready["apparmor"] == "Y"
        network = max((ROOT / "test-results/nas-parity/followup/vm-network").glob("fresh-*.json"))
        policy = read(network)
        assert policy["passed"] and policy["application_commit"] is None
        assert policy["route_before"] == policy["route_after"] and len(policy["networks"]) == 4
        destination.write_text(json.dumps({"ready": ready, "network_evidence": network.relative_to(ROOT).as_posix()}, indent=2) + "\n")
    pair_path = base / "graphato-ci/pair.json"
    if not pair_path.exists():
        # The first CI pair is created only when its recorded job is started.
        # Preserve the fresh-target evidence now and attach it after collection.
        return
    pair = read(pair_path)
    pair.setdefault("network_policy_evidence", {})[engine] = read(destination)["network_evidence"]
    pair_path.write_text(json.dumps(pair, indent=2) + "\n")


def main():
    base = ROOT / "test-results/nas-parity/followup/candidates/graphato" / COMMIT
    staged = read(base / "staged.json")
    assert staged["source_kind"] in {"observed_production_revision", "frozen_master_revision"}
    assert not staged["application_patches_applied"]
    destination = base / "current-source-comparison.json"
    assert not destination.exists(), "No implicit comparison repetition"
    before_path = base / "production-jobs-before.json"
    if not before_path.exists():
        before_path.write_text(json.dumps(production_jobs(), indent=2) + "\n")
    before = read(before_path)
    capture_preparation(base, "jenkins")
    bootstrap = base / "jenkins-bootstrap-watch.json"
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        if bootstrap.exists():
            state = read(bootstrap)
            assert all(row.get("result") == "SUCCESS" for row in state["builds"].values())
            break
        time.sleep(10)
    else:
        raise TimeoutError("Await the retained bootstrap result; no CI started")
    numbers = base / "jenkins-release-numbers.json"
    if not numbers.exists():
        phase("start_nas_graphato_candidate.py", "release", "--candidate", COMMIT)
    if not (base / "jenkins-release-watch.json").exists():
        phase("watch_nas_graphato_jenkins.py", "--candidate", COMMIT,
              "--builds", numbers.relative_to(ROOT).as_posix(), failed_result_allowed=True)
    reference = read(base / "jenkins-release-watch.json")
    capture_preparation(base, "jenkins")
    assert "graphato-ci" in reference["collected"]
    assert not any(row.get("building") for row in reference["builds"].values())
    if reference["builds"]["graphato-ci"]["result"] == "SUCCESS" and not (base / "graphato-ci/jenkins-final-state.json").exists():
        phase("nas_graphato_release_state.py", "jenkins", "--candidate", COMMIT)
    idle()
    assert inner("inspect", "jenkins-parity", "--format", "{{.Id}}").strip() == JENKINS_ID
    inner("stop", "--time", "120", "jenkins-parity", timeout=150)
    # Restore a new target even when Jenkins found a real failure; successful
    # candidate receipts cannot substitute for this unchanged-source counter-run.
    restore = ROOT / "test-results/nas-parity/vm-restores" / ("graphato-leroy-" + COMMIT[:12] + ".json")
    if not restore.exists():
        phase("restore_nas_vm.py", "graphato-leroy", "--candidate", COMMIT[:12])
        phase("prepare_nas_vm.py", "--candidate", COMMIT)
    capture_preparation(base, "leroy")
    phase("ensure_nas_target_tunnel.py", "--renew", "--hours", "12")
    bootstrap_pair = base / "graphato-bootstrap-host/pair.json"
    if not read(bootstrap_pair).get("leroy_run"):
        phase("compare_nas_job.py", "graphato-bootstrap-host", "start-leroy", "--candidate", COMMIT)
    run_id = read(bootstrap_pair)["leroy_run"]
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        with closing(client()) as api:
            response = api.get("/api/runs/" + run_id)
            response.raise_for_status()
            run = response.json()
        if run["status"] not in {"queued", "running", "waiting"}:
            phase("compare_nas_job.py", "graphato-bootstrap-host", "leroy", "--candidate", COMMIT)
            assert run["status"] == "succeeded", "Leroy bootstrap failed; no CI started"
            break
        time.sleep(10)
    else:
        raise TimeoutError("Leroy bootstrap still active")
    if not read(base / "graphato-ci/pair.json").get("leroy_run"):
        phase("compare_nas_job.py", "graphato-ci", "start-leroy", "--candidate", COMMIT)
    if not (base / "leroy-run-watch.json").exists():
        phase("watch_nas_graphato_leroy.py", "--candidate", COMMIT, failed_result_allowed=True)
    observed = read(base / "leroy-run-watch.json")
    assert not any(row["status"] in {"queued", "running", "waiting"} for row in observed["runs"].values())
    if observed["runs"]["graphato-ci"]["status"] == "succeeded" and not (base / "graphato-ci/leroy-final-state.json").exists():
        phase("nas_graphato_release_state.py", "leroy", "--candidate", COMMIT)
    after = production_jobs()
    (base / "production-jobs-after.json").write_text(json.dumps(after, indent=2) + "\n")
    record = {"at": datetime.now(timezone.utc).isoformat(), "commit": COMMIT,
              "application_patches_applied": False, "jenkins": reference, "leroy": observed,
              "fresh_target_per_engine": True, "background_guest_updates_disabled_both": True,
              "controller_and_workers_on_nas": True, "production_modified": False,
              "production_jobs_unchanged": before["jobs"] == after["jobs"], "production_cutover": False,
              "workload_success_both": all(row.get("result") == "SUCCESS" for row in reference["builds"].values())
              and observed["all_successful"], "receipt_and_failure_analysis_pending": True}
    destination.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
