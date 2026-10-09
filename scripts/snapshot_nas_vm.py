"""Save a clean baseline before either engine bootstraps Graphato."""

import json
import subprocess

from nas_ssh import ROOT
from prepare_nas_vm import guest


def main():
    evidence = ROOT / "test-results/nas-parity/vm-snapshot.json"
    if evidence.exists():
        raise RuntimeError("The comparison baseline snapshot already exists")
    guest("sudo test ! -e /opt/graphato/current; sudo systemctl poweroff --no-block")
    compose = ["docker", "compose", "-f", "infra/nas/compose.target-vm.yaml"]
    subprocess.run([*compose, "stop"], cwd=ROOT, check=True, timeout=300)
    info = json.loads(subprocess.check_output(["docker", "inspect", "leroy-nas-target-vm"]))[0]
    assert not info["State"]["Running"]
    subprocess.run(
        [
            *compose,
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "qemu-img",
            "vm",
            "snapshot",
            "-c",
            "nas-parity-base",
            "/vm/system.qcow2",
        ],
        cwd=ROOT,
        check=True,
    )
    evidence.write_text(
        json.dumps(
            {
                "snapshot": "nas-parity-base",
                "application_installed": False,
                "clean_shutdown": True,
                "volume": next(m["Name"] for m in info["Mounts"] if m["Destination"] == "/vm"),
            },
            indent=2,
        )
        + "\n"
    )
    subprocess.run([*compose, "up", "-d"], cwd=ROOT, check=True)
    print("Clean pre-bootstrap VM snapshot saved and VM restarted.")


if __name__ == "__main__":
    main()
