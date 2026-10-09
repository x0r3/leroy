"""Provision a fresh comparison VM while preserving the earlier acceptance disk."""

import json
import subprocess
import sys
from contextlib import closing

from test_support import ROOT, api


def main():
    with closing(api()) as client:
        for status in ("queued", "running", "waiting"):
            response = client.get("/api/runs", params={"status": status, "limit": 100})
            response.raise_for_status()
            if any(r["pipeline_id"].startswith("graphato-") for r in response.json()):
                raise RuntimeError("The earlier local Graphato environment still has active jobs")
    folder = ROOT / ".local/nas-parity/vm"
    config = folder / "config"
    config.mkdir(parents=True, exist_ok=True)
    for name in ("image.json", "user-data"):
        target = config / name
        if not target.exists():
            target.write_bytes((ROOT / ".local/vm/config" / name).read_bytes())
    (config / "meta-data").write_text(
        "instance-id: leroy-nas-parity\nlocal-hostname: leroy-nas-target\n", encoding="utf-8"
    )
    host_key = (ROOT / ".local/vm/ssh_host_ed25519_key.pub").read_text().strip()
    (folder / "known_hosts").write_text("[127.0.0.1]:2225 " + host_key + "\n", encoding="utf-8")
    original = json.loads(subprocess.check_output(["docker", "inspect", "leroy-linux-vm"]))[0]
    previous = next(m["Name"] for m in original["Mounts"] if m["Destination"] == "/vm")
    if original["State"]["Running"]:
        subprocess.run([sys.executable, "scripts/vm.py", "stop"], cwd=ROOT, check=True)
    assert (
        subprocess.check_output(
            ["docker", "inspect", "--format", "{{.State.Running}}", "leroy-linux-vm"]
        ).strip()
        == b"false"
    )
    subprocess.run(
        ["docker", "compose", "-f", "infra/nas/compose.target-vm.yaml", "up", "-d"], cwd=ROOT, check=True
    )
    print("Fresh comparison VM started; previous disk preserved:", previous, flush=True)
    (ROOT / "test-results/nas-parity/vm-provision.json").write_text(
        json.dumps(
            {
                "previous_disk_preserved": previous,
                "container": "leroy-nas-target-vm",
                "ssh_port": 2225,
                "source": json.loads((config / "image.json").read_text()),
                "application_patches_applied": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
