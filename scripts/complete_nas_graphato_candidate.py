"""Continue a recorded successful Jenkins candidate on a fresh Leroy target.

This is a single bounded acceptance sequence, not a scheduled task. It never
retries failed jobs or restores the VM while either engine still uses it.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from contextlib import closing

from compare_nas_antares import client
from nas_followup_support import inner, wait_production_build
from nas_gitea_target import idle
from nas_ssh import ROOT


def read(path):
    return json.loads(path.read_text())


def phase(script, *args):
    print("Counter-run phase:", script, *args, flush=True)
    subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), *args],
        cwd=ROOT, check=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--jenkins-network-evidence", required=True)
    args = parser.parse_args()
    candidate = args.candidate
    assert re.fullmatch("[a-f0-9]{40}", candidate)
    base = ROOT / "test-results/nas-parity/followup/candidates/graphato" / candidate
    assert read(base / "staged.json")["commit"] == candidate
    policies = ROOT / "test-results/nas-parity/followup/vm-network"
    jenkins_policy = (ROOT / args.jenkins_network_evidence).resolve(strict=True)
    assert jenkins_policy.is_relative_to(policies.resolve())
    policy = read(jenkins_policy)
    assert policy["passed"] and policy["application_commit"] is None
    assert policy["pool"] == [{"base": "10.211.0.0/16", "size": 24}]
    if (base / "complete-pair.json").exists():
        assert read(base / "complete-pair.json")["pipelines_successful"]
        print("Recorded comparison already complete; no jobs started.")
        return
    print("Waiting for the recorded Jenkins suites and final target evidence.", flush=True)
    deadline = time.monotonic() + 9 * 3600
    while time.monotonic() < deadline:
        watch = base / "jenkins-release-watch.json"
        final = base / "graphato-ci/jenkins-final-state.json"
        if watch.exists():
            result = read(watch)
            assert result["candidate"] == candidate
            assert all(row.get("result") == "SUCCESS" for row in result["builds"].values()), (
                "Jenkins failed; preserve target and inspect the actual failure"
            )
            if final.exists():
                assert read(final)["receipt"]["status"] == "verified"
                if not json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}")):
                    break
        bootstrap = base / "jenkins-bootstrap-watch.json"
        if bootstrap.exists():
            assert all(row.get("result") == "SUCCESS" for row in read(bootstrap)["builds"].values())
        time.sleep(30)
    else:
        raise TimeoutError("Jenkins evidence incomplete; no target restored or job retried")

    bootstrap_pair = base / "graphato-bootstrap-host/pair.json"
    ci_pair = base / "graphato-ci/pair.json"
    if not read(bootstrap_pair).get("leroy_run"):
        wait_production_build()
        idle()
        phase("ensure_nas_target_tunnel.py", "--renew", "--hours", "12")
        restored = ROOT / "test-results/nas-parity/vm-restores" / (
            "graphato-leroy-" + candidate[:12] + ".json"
        )
        if not restored.exists():
            phase("restore_nas_vm.py", "graphato-leroy", "--candidate", candidate[:12])
        prepared = base / "leroy-infrastructure-ready.json"
        if not prepared.exists():
            before = set(policies.glob("fresh-*.json"))
            phase("prepare_nas_vm.py")
            (leroy_policy,) = set(policies.glob("fresh-*.json")) - before
            checked = read(leroy_policy)
            assert checked["passed"] and checked["application_commit"] is None
            assert checked["pool"] == policy["pool"]
            prepared.write_text(json.dumps({
                "restore": restored.relative_to(ROOT).as_posix(),
                "network_policy_evidence": {
                    "jenkins": jenkins_policy.relative_to(ROOT).as_posix(),
                    "leroy": leroy_policy.relative_to(ROOT).as_posix(),
                },
            }, indent=2) + "\n")
        environment = read(prepared)["network_policy_evidence"]
        for path in base.glob("graphato-*/pair.json"):
            pair = read(path)
            pair["network_policy_evidence"] = environment
            path.write_text(json.dumps(pair, indent=2) + "\n")
        phase("compare_nas_job.py", "graphato-bootstrap-host", "start-leroy", "--candidate", candidate)
    bootstrap_id = read(bootstrap_pair)["leroy_run"]
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        with closing(client()) as api:
            response = api.get("/api/runs/" + bootstrap_id)
            response.raise_for_status()
            run = response.json()
        if run["status"] not in {"queued", "running", "waiting"}:
            phase("compare_nas_job.py", "graphato-bootstrap-host", "leroy", "--candidate", candidate)
            assert run["status"] == "succeeded", "Fresh bootstrap failed; no CI started"
            break
        time.sleep(10)
    else:
        raise TimeoutError("Bootstrap still active; no CI started")
    if not read(ci_pair).get("leroy_run"):
        wait_production_build()
        phase("compare_nas_job.py", "graphato-ci", "start-leroy", "--candidate", candidate)
    phase("watch_nas_graphato_leroy.py", "--candidate", candidate)
    phase("nas_graphato_release_state.py", "leroy", "--candidate", candidate)
    phase("compare_nas_graphato.py", "--candidate", candidate)
    phase("summarize_nas_followup.py")
    comparison = read(base / "comparison.json")
    assert comparison["workload_success_both"] and comparison["docker_network_policy_matched"]
    (base / "complete-pair.json").write_text(json.dumps({
        "candidate": candidate, "pipelines_successful": True,
        "comparison": "comparison.json", "production_cutover": False,
        "scope": "Graphato candidate only; Antares and overall readiness remain separate",
    }, indent=2) + "\n")
    print("Complete Graphato pair verified. No production cutover performed.", flush=True)


if __name__ == "__main__":
    main()
