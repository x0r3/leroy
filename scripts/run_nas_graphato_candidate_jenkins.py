"""Run one explicitly prepared candidate, preserving recorded builds on resume."""

import argparse
import json
import re
import subprocess
import sys

from nas_followup_support import inner, jenkins_api, start_jenkins, wait_production_build
from nas_gitea_target import idle
from nas_ssh import ROOT
from watch_nas_graphato_via_leroy import JENKINS_ID


def phase(script, *args, check=True):
    print("Candidate phase:", script, *args, flush=True)
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), *args],
        cwd=ROOT, check=check,
    ).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--previous", required=True)
    args = parser.parse_args()
    assert all(re.fullmatch("[a-f0-9]{40}", value) for value in (args.candidate, args.previous))
    base = ROOT / "test-results/nas-parity/followup/candidates/graphato" / args.candidate
    staged = json.loads((base / "staged.json").read_text())
    assert staged["commit"] == args.candidate and staged["jenkinsfiles_unchanged"]
    assert (ROOT / "test-results/nas-parity/vm-restores" /
            ("graphato-jenkins-" + args.candidate[:12] + ".json")).is_file()
    if not (base / "activated.json").exists():
        wait_production_build()
        idle()
        start_jenkins()
        head = subprocess.check_output(
            ["git", "-C", str(ROOT / ".sources/graphato-nas-validation"), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        assert head == args.candidate
        phase("activate_nas_graphato_candidate.py", "--previous", args.previous)
    for label in ("bootstrap", "release"):
        numbers = base / ("jenkins-" + label + "-numbers.json")
        if not numbers.exists():
            phase("start_nas_graphato_candidate.py", label, "--candidate", args.candidate)
        code = phase(
            "watch_nas_graphato_jenkins.py", "--candidate", args.candidate,
            "--builds", numbers.relative_to(ROOT).as_posix(), check=False,
        )
        if code:
            raise SystemExit("Recorded Jenkins failure or observation error; inspect evidence before proceeding.")
    phase("nas_graphato_release_state.py", "jenkins", "--candidate", args.candidate)
    idle()
    assert not json.loads(jenkins_api("/queue/api/json?tree=items[id]")["text"])["items"]
    assert inner("inspect", "jenkins-parity", "--format", "{{.Id}}").strip() == JENKINS_ID
    inner("stop", "--time", "120", "jenkins-parity", timeout=150)
    print("Jenkins candidate completed and stopped. Fresh Leroy counter-run remains.", flush=True)


if __name__ == "__main__":
    main()
