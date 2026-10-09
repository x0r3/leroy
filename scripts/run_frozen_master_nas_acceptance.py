"""Run the explicitly frozen master comparison; preserve every failed attempt."""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

from nas_ssh import ROOT


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def phase(script, *arguments, failure_allowed=False):
    print("Frozen master acceptance:", script, *arguments, flush=True)
    result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), *arguments], cwd=ROOT)
    if result.returncode and not failure_allowed:
        raise RuntimeError("Inspect the retained phase before any explicit retry: " + script)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--resume", action="store_true", help="Resume recorded completed preparation, never repeat a started comparison")
    args = parser.parse_args()
    commit = args.commit
    assert re.fullmatch(r"[a-f0-9]{40}", commit)
    os.environ["LEROY_NAS_FROZEN_GRAPHATO_COMMIT"] = commit
    from compare_current_nas_graphato import main as compare_fresh
    from nas_followup_support import inner, start_jenkins
    from nas_gitea_target import idle
    from nas_master_build_slot import wait_for_nas_build_slot

    base = ROOT / "test-results/nas-parity/followup/candidates/graphato" / commit
    frozen = read(base / "frozen-master.json")
    assert frozen["commit"] == commit and not frozen["application_patches_applied"]
    progress = base / "master-acceptance-progress.json"
    if progress.exists():
        assert args.resume, "Use an explicit resume after inspecting the recorded phase"
        assert read(progress)["commit"] == commit
    else:
        assert not args.resume
        write(progress, {"commit": commit, "started_at": datetime.now(timezone.utc).isoformat(), "phase": "preparing"})
    assert not (base / "master-acceptance-complete.json").exists()
    idle()
    restore = ROOT / "test-results/nas-parity/vm-restores" / ("graphato-jenkins-" + commit[:12] + ".json")
    if not restore.exists():
        phase("restore_nas_vm.py", "graphato-jenkins", "--candidate", commit[:12])
        phase("prepare_nas_vm.py", "--candidate", commit)
        write(base / "jenkins-infrastructure-ready.json", {"commit": commit, "passed": True})
    assert read(base / "jenkins-infrastructure-ready.json")["passed"]
    phase("ensure_nas_target_tunnel.py", "--renew", "--hours", "24")
    write(progress, {"commit": commit, "at": datetime.now(timezone.utc).isoformat(), "phase": "awaiting_nas_compiler_slot"})
    wait_for_nas_build_slot()
    start_jenkins()
    if not (base / "activated.json").exists():
        previous = inner("exec", "gitea", "git", "--git-dir=/data/git/repositories/gitea-admin/graphato.git",
                         "rev-parse", "refs/heads/master").strip()
        assert re.fullmatch(r"[a-f0-9]{40}", previous)
        phase("activate_nas_graphato_candidate.py", "--previous", previous,
              "--checkout", frozen["checkout"], "--frozen-master-source")
    if not (base / "jenkins-bootstrap-numbers.json").exists():
        phase("start_nas_graphato_candidate.py", "bootstrap", "--candidate", commit)
    if not (base / "jenkins-bootstrap-watch.json").exists():
        phase("watch_nas_graphato_jenkins.py", "--candidate", commit, "--builds",
              (base / "jenkins-bootstrap-numbers.json").relative_to(ROOT).as_posix())
    if not (base / "current-source-comparison.json").exists():
        write(progress, {"commit": commit, "at": datetime.now(timezone.utc).isoformat(), "phase": "fresh_target_comparison"})
        compare_fresh()
    phase("compare_nas_graphato.py", "--candidate", commit, "--delivery-only")
    phase("analyze_frozen_master_nas_graphato.py", "--commit", commit)
    scenario = base / "scenarios/root-private-existing-host"
    if not (scenario / "executions.json").exists():
        assert not scenario.exists(), "A started prepared-host comparison requires inspection before resuming"
        write(progress, {"commit": commit, "at": datetime.now(timezone.utc).isoformat(), "phase": "prepared_host_full_groups"})
        phase("compare_existing_host_nas_graphato.py", "all")
    phase("audit_nas_production_activity.py")
    phase("analyze_existing_host_nas_graphato.py")
    write(base / "master-acceptance-complete.json", {
        "at": datetime.now(timezone.utc).isoformat(), "commit": commit,
        "fresh_target": "current-source-analysis.json", "prepared_host": "scenarios/root-private-existing-host/analysis.json",
        "application_patches_applied": False, "production_modified": False,
        "manual_visual_review_pending": True, "final_operations_acceptance_pending": True})
    print("Frozen master execution comparisons complete; UI and final operations checks remain.", flush=True)


if __name__ == "__main__":
    main()
