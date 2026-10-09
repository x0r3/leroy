"""Record exact build numbers before starting one owned candidate phase."""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone

from compare_nas_antares import jenkins_python
from nas_candidate_paths import comparison_source
from nas_followup_support import jenkins_api, start_jenkins, wait_production_build
from nas_gitea_target import idle
from nas_ssh import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["bootstrap", "release"])
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--retry-bootstrap-reason", help="Explicit recovery of a recorded failed bootstrap")
    args = parser.parse_args()
    _, folder = comparison_source("graphato-ci", args.candidate)
    base = folder.parent
    marker = base / ("jenkins-" + args.phase + "-numbers.json")
    retry = args.retry_bootstrap_reason is not None
    if retry:
        assert args.phase == "bootstrap" and args.retry_bootstrap_reason.strip()
        previous_numbers = json.loads(marker.read_text())
        previous_watch = json.loads((base / "jenkins-bootstrap-watch.json").read_text())
        previous_pair = json.loads((base / "graphato-bootstrap-host/pair.json").read_text())
        previous_build = previous_pair["jenkins"]
        assert set(previous_numbers) == {"graphato-bootstrap-host"}
        assert previous_numbers["graphato-bootstrap-host"] == previous_build["number"]
        assert previous_watch["builds"]["graphato-bootstrap-host"]["result"] == "FAILURE"
        assert previous_build["result"] == "FAILURE" and not previous_build["building"]
        assert not previous_pair.get("leroy_run") and not (base / "jenkins-release-numbers.json").exists()
    else:
        assert not marker.exists(), "Inspect the recorded attempt; no implicit retry"
    idle()
    if args.phase == "bootstrap":
        pair_path = folder / "pair.json"
        pair = json.loads(pair_path.read_text()) if pair_path.exists() else {}
        attempt = pair.get("jenkins_vm_restore_attempt")
        suffix = "-" + attempt if attempt else ""
        restore = (
            ROOT
            / "test-results/nas-parity/vm-restores"
            / ("graphato-jenkins-" + args.candidate[:12] + suffix + ".json")
        )
        assert restore.is_file(), "Prepare and verify a fresh owned target first"
        jobs = ["graphato-bootstrap-host"]
    else:
        bootstrap = json.loads((base / "graphato-bootstrap-host/pair.json").read_text())
        assert bootstrap["jenkins"]["result"] == "SUCCESS" and not bootstrap["jenkins"]["building"]
        jobs = [
            "graphato-ci",
            "graphato-release-acceptance",
            "graphato-postdeploy-web",
            "graphato-postdeploy-quality",
        ]
    if json.loads((base / "staged.json").read_text())["source_kind"] == "frozen_master_revision":
        from nas_master_build_slot import wait_for_nas_build_slot

        wait_for_nas_build_slot()
    else:
        wait_production_build()
    start_jenkins()
    state = json.loads(jenkins_api("/api/json?tree=jobs[name,nextBuildNumber,lastBuild[building]]")["text"])
    assert not any((job.get("lastBuild") or {}).get("building") for job in state["jobs"])
    assert not json.loads(jenkins_api("/queue/api/json?tree=items[id]")["text"])["items"]
    if args.phase == "bootstrap":
        # A live local ssh.exe is not evidence that a remote forwarding listener
        # or its destination is usable. Exercise the actual job transport first.
        transport = json.loads(jenkins_python("""import json,subprocess
output=subprocess.check_output(['ssh','-i','/root/.ssh/parity-bootstrap','-o','ConnectTimeout=10','-o','UserKnownHostsFile=/dev/null','root@87.106.133.233','uname -r; systemd-detect-virt; test ! -e /opt/graphato/current && echo fresh-target'],text=True,timeout=25)
assert output.splitlines()==['6.8.0-142-generic','kvm','fresh-target']
print(json.dumps({'ssh_from_test_jenkins':True,'host_key_pinned_by_ssh_config':True,'fresh_target':True}))
""", timeout=40))
        number = next(job["nextBuildNumber"] for job in state["jobs"] if job["name"] == jobs[0])
        (base / ("jenkins-bootstrap-transport-" + str(number) + ".json")).write_text(
            json.dumps({**transport, "checked_at": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n"
        )
    if retry:
        recorded = next(job for job in state["jobs"] if job["name"] == "graphato-bootstrap-host")
        assert recorded["nextBuildNumber"] == previous_build["number"] + 1
        archive = base / "attempts" / ("jenkins-bootstrap-" + str(previous_build["number"]))
        archive.mkdir(parents=True, exist_ok=False)
        for path in (marker, base / "jenkins-bootstrap-watch.json", base / "graphato-bootstrap-host/pair.json"):
            (archive / path.name).write_bytes(path.read_bytes())
        (archive / "recovery.json").write_text(json.dumps({
            "reason": args.retry_bootstrap_reason, "fresh_target_checked": True,
            "production_changed": False, "recorded_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2) + "\n")
        # The previous failure remains in the immutable attempt directory. Do
        # not leave it in the active watch slot while observing the new build.
        (base / "jenkins-bootstrap-watch.json").unlink()
    numbers = {job["name"]: job["nextBuildNumber"] for job in state["jobs"] if job["name"] in jobs}
    assert set(numbers) == set(jobs)
    marker.write_text(json.dumps(numbers, indent=2) + "\n")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/compare_nas_job.py"),
            jobs[0],
            "retry-jenkins" if retry else "start-jenkins",
            "--candidate",
            args.candidate,
            *(["--reason", args.retry_bootstrap_reason] if retry else []),
        ],
        check=True,
    )
    print(
        json.dumps(
            {
                "candidate": args.candidate,
                "builds": numbers,
                "watch_file": marker.relative_to(ROOT).as_posix(),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
