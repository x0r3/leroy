"""Connect the fresh Windows test VM to the owned NAS comparison network."""

import json
import subprocess
import time

from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE, remote
from nas_ssh import ROOT, upload_file


def main():
    state = LOCAL / "vm/tunnel.json"
    if state.exists():
        raise RuntimeError("A tunnel was already recorded; inspect it before starting another")
    for name in ("tunnel-key", "tunnel-host"):
        key = LOCAL / "vm" / name
        if not key.exists():
            subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(key)],
                stdout=subprocess.DEVNULL,
                check=True,
            )
    config = LOCAL / "config/vm-access"
    config.mkdir(exist_ok=True)
    (config / "host_key").write_bytes((LOCAL / "vm/tunnel-host").read_bytes())
    (config / "authorized_keys").write_bytes((LOCAL / "vm/tunnel-key.pub").read_bytes())
    (config / "sshd_config").write_bytes((ROOT / "infra/nas/sshd.vm-access.conf").read_bytes())
    (LOCAL / "vm/tunnel-known-hosts").write_text(
        "[192.168.178.97]:12226 " + (LOCAL / "vm/tunnel-host.pub").read_text()
    )
    remote(f"mkdir -p {REMOTE}/config/vm-access\n")
    for path in config.iterdir():
        upload_file(path, REMOTE + "/config/vm-access/" + path.name, CREDENTIALS)
    for name in ("Dockerfile.vm-access", "compose.vm-access.yaml"):
        upload_file(ROOT / "infra/nas" / name, REMOTE + "/" + name, CREDENTIALS)
    upload_file(ROOT / "infra/nas/dind.sh", REMOTE + "/dind-next.sh", CREDENTIALS)
    # Update the existing bind-mounted inode and its live namespace, without
    # restarting the daemon or interrupting another owned comparison build.
    remote(f"""cd {REMOTE}
test -f .leroy-owned
cat dind-next.sh > dind.sh
chmod 644 compose.vm-access.yaml dind.sh
docker exec leroy-nas-parity-docker-1 sh -c 'iptables -D LEROY-PARITY-EGRESS -d 10.232.98.1 -p tcp --dport 12225 -j RETURN 2>/dev/null || true'
docker exec leroy-nas-parity-docker-1 sh -c 'iptables -C LEROY-PARITY-EGRESS -d 10.232.98.11 -p tcp --dport 12225 -j RETURN 2>/dev/null || iptables -I LEROY-PARITY-EGRESS 2 -d 10.232.98.11 -p tcp --dport 12225 -j RETURN'
docker build -f Dockerfile.vm-access -t leroy-vm-access:nas-parity .
docker compose -f compose.yaml -f compose.vm-access.yaml up -d --no-deps vm-access
""")
    command = [
        "ssh",
        "-N",
        "-T",
        "-i",
        str(LOCAL / "vm/tunnel-key"),
        "-p",
        "12226",
        "-o",
        "UserKnownHostsFile=" + str(LOCAL / "vm/tunnel-known-hosts"),
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        "ExitOnForwardFailure=yes",
        "-R",
        "10.232.98.11:12225:127.0.0.1:2225",
        "root@192.168.178.97",
    ]
    with (LOCAL / "vm/tunnel.log").open("wb") as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    time.sleep(3)
    if process.poll() is not None:
        raise RuntimeError("Reverse tunnel failed; inspect the local tunnel log")
    state.write_text(json.dumps({"pid": process.pid, "remote_port": 12225, "local_port": 2225}) + "\n")
    print("Reverse SSH tunnel started; the NAS bridge exposes only the isolated VM SSH port.")


if __name__ == "__main__":
    main()
