"""Restore the clean test baseline after preserving the completed VM state."""

import argparse
import json
import re
import subprocess
from contextlib import closing

from compare_nas_antares import client
from nas_gitea_target import idle
from nas_ssh import ROOT
from prepare_nas_vm import guest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("purpose", choices=["hub-jenkins", "hub-leroy", "graphato-jenkins", "graphato-leroy"])
    parser.add_argument(
        "--candidate", help="Separate checkpoint for an explicit 12-character candidate commit"
    )
    parser.add_argument(
        "--via-leroy", action="store_true", help="Quiesce the completed Graphato baseline through Leroy"
    )
    parser.add_argument("--attempt", help="Explicit fresh attempt; preserves a separate target snapshot")
    args = parser.parse_args()
    via_leroy = None
    if args.candidate:
        assert args.purpose.startswith("graphato-") and re.fullmatch("[a-f0-9]{12}", args.candidate)
        args.purpose += "-" + args.candidate
    base_purpose = args.purpose
    if args.attempt:
        assert args.candidate and re.fullmatch("[a-z][a-z0-9-]{0,39}", args.attempt)
        args.purpose += "-" + args.attempt
    folder = ROOT / "test-results/nas-parity/vm-restores"
    folder.mkdir(exist_ok=True)
    marker = folder / (args.purpose + ".json")
    if marker.exists():
        raise RuntimeError("This baseline restoration was already recorded")
    if args.via_leroy:
        from quiesce_nas_jenkins_via_leroy import quiesce

        assert args.candidate and base_purpose == "graphato-leroy-" + args.candidate
        candidates = list(
            (ROOT / "test-results/nas-parity/followup/candidates/graphato").glob(args.candidate + "*")
        )
        assert len(candidates) == 1 and re.fullmatch("[a-f0-9]{40}", candidates[0].name)
        via_leroy = quiesce(candidates[0].name)
        with closing(client()) as api:
            for status in ("running", "queued", "waiting"):
                response = api.get("/api/runs", params={"status": status, "limit": 100})
                response.raise_for_status()
                assert not response.json(), "Complete the current Leroy comparison first"
            response = api.get("/api/pipelines")
            response.raise_for_status()
            assert not any(pipeline["enabled"] for pipeline in response.json())
    else:
        idle()
    previous = json.loads(subprocess.check_output(["docker", "inspect", "leroy-nas-target-vm"]))[0]
    assert next(m["Name"] for m in previous["Mounts"] if m["Destination"] == "/vm") == "leroy-nas-target_disk"
    if previous["State"]["Running"]:
        guest("sudo python3 - stop", (ROOT / "infra/vm/graphato-lifecycle.py").read_text(), timeout=240)
        guest(
            "sudo sh -c 'containers=$(docker ps -q --filter label=com.docker.compose.project=nikicas-hub); if [ -n \"$containers\" ]; then docker stop --time 60 $containers; fi; systemctl poweroff --no-block'",
            timeout=180,
        )
    compose = ["docker", "compose", "-f", "infra/nas/compose.target-vm.yaml"]
    subprocess.run([*compose, "stop"], cwd=ROOT, check=True, timeout=300)
    info = json.loads(subprocess.check_output(["docker", "inspect", "leroy-nas-target-vm"]))[0]
    assert not info["State"]["Running"]
    assert next(m["Name"] for m in info["Mounts"] if m["Destination"] == "/vm") == "leroy-nas-target_disk"
    command = [*compose, "run", "--rm", "--no-deps", "--entrypoint", "qemu-img", "vm", "snapshot"]
    snapshot = "before-" + args.purpose
    subprocess.run([*command, "-c", snapshot, "/vm/system.qcow2"], cwd=ROOT, check=True)
    subprocess.run([*command, "-a", "nas-parity-base", "/vm/system.qcow2"], cwd=ROOT, check=True)
    marker.write_text(
        json.dumps(
            {
                "restored": "nas-parity-base",
                "previous_state_preserved": snapshot,
                "volume": "leroy-nas-target_disk",
                "purpose": args.purpose,
                "quiesced_via_leroy": via_leroy,
                "already_stopped": not previous["State"]["Running"],
                "previous_container_exit_code": previous["State"]["ExitCode"],
            },
            indent=2,
        )
        + "\n"
    )
    subprocess.run([*compose, "up", "-d"], cwd=ROOT, check=True)
    print("Clean VM baseline restored for", args.purpose)


if __name__ == "__main__":
    main()
