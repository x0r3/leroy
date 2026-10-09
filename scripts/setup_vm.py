"""Create Leroy's isolated Ubuntu VM using existing Docker Desktop KVM access."""

import hashlib
import json
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from vm import compose_args

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local/vm"
IMAGE_URL = "https://cloud-images.ubuntu.com/releases/noble/release/"
IMAGE_NAME = "ubuntu-24.04-server-cloudimg-amd64.img"


def download(url, destination):
    partial = destination.with_suffix(destination.suffix + ".download")
    request = urllib.request.Request(url, headers={"User-Agent": "Leroy-isolated-vm-setup"})
    with urllib.request.urlopen(request, timeout=120) as source, partial.open("wb") as target:
        while data := source.read(1024 * 1024):
            target.write(data)
    partial.replace(destination)


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


def main():
    config, cache = LOCAL / "config", LOCAL / "cache"
    config.mkdir(parents=True, exist_ok=True)
    cache.mkdir(exist_ok=True)
    key = LOCAL / "id_ed25519"
    host_key = LOCAL / "ssh_host_ed25519_key"
    for path, comment in ((key, "leroy-vm-admin"), (host_key, "leroy-vm-host")):
        if not path.exists():
            run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", comment, "-f", str(path))
    public = key.with_suffix(".pub").read_text().strip()
    host_public = host_key.with_suffix(".pub").read_text().strip()
    (LOCAL / "known_hosts").write_text("[127.0.0.1]:2224 " + host_public + "\n", encoding="utf-8")
    manifest_path = config / "image.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        download(IMAGE_URL + "SHA256SUMS", cache / "SHA256SUMS")
        checksum = next(
            line.split()[0]
            for line in (cache / "SHA256SUMS").read_text().splitlines()
            if line.split()[-1].lstrip("*") == IMAGE_NAME
        )
        manifest = {
            "filename": IMAGE_NAME,
            "url": IMAGE_URL + IMAGE_NAME,
            "sha256": checksum,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }
    disk = cache / IMAGE_NAME
    if not disk.exists():
        print("Downloading official Ubuntu 24.04 cloud image (approximately 600 MiB)", flush=True)
        download(manifest["url"], disk)
    with disk.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != manifest["sha256"]:
            raise RuntimeError("Cloud image checksum mismatch; existing files preserved")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if not (config / "user-data").exists():
        data = {
            "hostname": "leroy-test-vm",
            "manage_etc_hosts": True,
            "disable_root": True,
            "ssh_pwauth": False,
            "ssh_deletekeys": False,
            "ssh_keys": {"ed25519_private": host_key.read_text(), "ed25519_public": host_public},
            "users": [
                {
                    "name": "leroy-admin",
                    "groups": ["adm", "sudo"],
                    "shell": "/bin/bash",
                    "lock_passwd": True,
                    "sudo": ["ALL=(ALL) NOPASSWD:ALL"],
                    "ssh_authorized_keys": [public],
                }
            ],
            "package_update": True,
            "package_upgrade": False,
            "packages": [
                "apparmor",
                "apparmor-utils",
                "ca-certificates",
                "curl",
                "git",
                "jq",
                "python3",
                "uidmap",
                "dbus-user-session",
                "slirp4netns",
            ],
            "write_files": [
                {
                    "path": "/usr/local/sbin/leroy-vm-provision",
                    "permissions": "0700",
                    "content": (ROOT / "infra/vm/provision.sh").read_text(encoding="utf-8"),
                }
            ],
            "runcmd": [["bash", "/usr/local/sbin/leroy-vm-provision"]],
        }
        (config / "user-data").write_text("#cloud-config\n" + json.dumps(data, indent=2), encoding="utf-8")
        (config / "meta-data").write_text(
            json.dumps({"instance-id": "leroy-vm-01", "local-hostname": "leroy-test-vm"}), encoding="utf-8"
        )
    run(*compose_args(), "up", "-d", "--build")
    print("VM started. SSH: python scripts/vm.py ssh ; bootstrap logs: python scripts/vm.py console")


if __name__ == "__main__":
    main()
