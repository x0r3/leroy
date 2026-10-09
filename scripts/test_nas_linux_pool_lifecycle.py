"""Verify owned Linux pool restart and encrypted configuration/volume restore."""

import argparse
import hashlib
import hmac
import io
import json
import secrets
import subprocess
import tarfile
import time
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from nas_followup_support import production_jobs
from nas_ssh import ROOT
from setup_nas_linux_pool import COMMIT, EVIDENCE, LOCAL, PARENT, docker, nested

RUNNER = "leroy-nas-linux-runner"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", choices=["state-only"], help="Explicit retry retaining the oversized workspace backup")
    attempt = parser.parse_args().attempt
    folder = EVIDENCE / "lifecycle"
    if attempt:
        assert json.loads((folder / "report.json").read_text())["passed"] is False
        folder = folder / "attempts" / attempt
    folder.mkdir(parents=True, exist_ok=True)
    assert not (folder / "started.json").exists(), "Inspect existing lifecycle evidence before retrying"
    pool = json.loads((EVIDENCE / "pool.json").read_text())
    parent = json.loads(docker("inspect", PARENT, text=True).stdout)[0]
    supervisor = json.loads(docker("inspect", RUNNER, text=True).stdout)[0]
    assert parent["Id"] == pool["parent_id"] and parent["State"]["Running"]
    assert supervisor["Config"]["Labels"]["io.leroy.nas-linux-pool"] == "true"
    assert supervisor["HostConfig"]["NetworkMode"] in ("container:" + PARENT, "container:" + parent["Id"])
    with closing(client()) as api:
        for status in ("queued", "running", "waiting"):
            response = api.get("/api/runs", params={"status": status})
            response.raise_for_status()
            assert not response.json()
        response = api.get("/api/pipelines")
        response.raise_for_status()
        assert not any(p["enabled"] for p in response.json())
    children = json.loads(nested("inspect", "jenkins-parity", "gitea", text=True).stdout)
    assert children[0]["Id"] == pool["jenkins_id"] and not children[0]["State"]["Running"]
    assert nested("ps", "--format", "{{.Names}}", text=True).stdout.strip() == "gitea"
    before = production_jobs()
    (folder / "started.json").write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(),
        "parent_id": parent["Id"], "runner_id": supervisor["Id"], "production_read_only": True}) + "\n")

    # The NAS already backs up controller state. Workers need reproducible
    # images, sources and configuration; do not back up replaceable build caches.
    files = [LOCAL / "dind.sh", LOCAL / "runner.toml", *sorted((LOCAL / "fixtures").glob("*"))]
    assert all(path.is_file() and path.resolve().is_relative_to(LOCAL.resolve()) for path in files)
    token = ROOT / ".local/nas-parity/config/runner_token"
    archive = io.BytesIO()
    expected = {}
    with tarfile.open(fileobj=archive, mode="w:gz") as bundle:
        for path in files + [token]:
            name = path.relative_to(LOCAL).as_posix() if path != token else "secrets/runner_token"
            raw = path.read_bytes()
            expected[name] = hashlib.sha256(raw).hexdigest()
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode = len(raw), 0o600
            bundle.addfile(entry, io.BytesIO(raw))
    suffix = "-" + attempt if attempt else ""
    key = LOCAL / ("lifecycle-backup-key" + suffix)
    assert not key.exists()
    key.write_text(secrets.token_urlsafe(48) + "\n")
    openssl = "C:/Program Files/Git/usr/bin/openssl.exe"
    args = [openssl, "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-pass", "file:" + str(key)]
    encrypted = subprocess.run(args, input=archive.getvalue(), capture_output=True, check=True).stdout
    backup = LOCAL / ("lifecycle-configuration" + suffix + ".enc")
    backup.write_bytes(encrypted)
    tag = hmac.new(key.read_bytes(), encrypted, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(tag, hmac.new(key.read_bytes(), backup.read_bytes(), hashlib.sha256).hexdigest())
    restored = subprocess.run([*args[:2], "-d", *args[2:]], input=backup.read_bytes(), capture_output=True, check=True).stdout
    recovered = {}
    with tarfile.open(fileobj=io.BytesIO(restored), mode="r:gz") as bundle:
        for entry in bundle:
            assert entry.isfile() and entry.name in expected
            recovered[entry.name] = hashlib.sha256(bundle.extractfile(entry).read()).hexdigest()
    assert recovered == expected

    # Preserve comparison Jenkins records and validate restoration to a new,
    # explicitly labelled volume. Never overwrite the original home volume.
    restore_volume = "leroy-nas-linux-lifecycle-restore" + suffix
    assert nested("volume", "inspect", restore_volume, check=False).returncode != 0
    helper = ["run", "--rm", "--network", "none", "--memory", "256m", "--cpus", "0.5",
              "--label", "io.leroy.nas-linux-pool=true", "--entrypoint", "sh"]
    saved = nested(*helper, "-v", "jenkins-parity-aligned-home:/input:ro", "leroy-job:nas-parity",
                   "-c", "cd /input && tar --exclude=./workspace --exclude=./caches --exclude=./war -czf - .", timeout=180).stdout
    if len(saved) >= 512 * 1024**2:
        (folder / "report.json").write_text(json.dumps({"passed": False,
            "reason": "Jenkins archive exceeded the explicit 512-MiB bound", "archive_bytes": len(saved),
            "pool_restart_started": False, "production_modified": False}) + "\n")
        raise ValueError("Retain the oversized backup attempt; no restart started")
    home_backup = LOCAL / ("lifecycle-jenkins-home" + suffix + ".enc")
    home_backup.write_bytes(subprocess.run(args, input=saved, capture_output=True, check=True).stdout)
    home_tag = hmac.new(key.read_bytes(), home_backup.read_bytes(), hashlib.sha256).hexdigest()
    home_restored = subprocess.run([*args[:2], "-d", *args[2:]], input=home_backup.read_bytes(), capture_output=True, check=True).stdout
    assert home_restored == saved
    nested("volume", "create", "--label", "io.leroy.nas-linux-lifecycle-restore=true", restore_volume)
    try:
        nested(*helper, "-i", "-v", restore_volume + ":/restore", "leroy-job:nas-parity",
               "-c", "cd /restore && tar -xzf -", input=home_restored, timeout=180)
        fingerprint = "import hashlib,json,pathlib;root=pathlib.Path('/input');print(json.dumps({p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.relative_to(root).parts[0] not in ('workspace','caches','war') and p.is_file() and not p.is_symlink()},sort_keys=True))"
        def files_in(volume):
            return json.loads(nested("run", "--rm", "--network", "none", "--memory", "256m", "--cpus", "0.5",
                                     "--label", "io.leroy.nas-linux-pool=true", "-v", volume + ":/input:ro",
                                     "--entrypoint", "python3", "leroy-job:nas-parity", "-c", fingerprint,
                                     text=True, timeout=180).stdout)
        original_files = files_in("jenkins-parity-aligned-home")
        assert original_files == files_in(restore_volume)
        assert "jobs/antares-ci/builds/1/build.xml" in original_files
    finally:
        volume = json.loads(nested("volume", "inspect", restore_volume, text=True).stdout)[0]
        assert volume["Labels"]["io.leroy.nas-linux-lifecycle-restore"] == "true"
        nested("volume", "rm", restore_volume)

    docker("update", "--restart", "unless-stopped", PARENT, RUNNER)
    nested("update", "--restart", "unless-stopped", "gitea")
    docker("stop", RUNNER)
    nested("stop", "gitea")
    docker("stop", PARENT, timeout=90)
    assert not json.loads(docker("inspect", PARENT, text=True).stdout)[0]["State"]["Running"]
    docker("start", PARENT)
    for _ in range(90):
        probe = docker("exec", PARENT, "sh", "-c", "test -f /run/leroy-isolation-ready && docker info >/dev/null 2>&1", check=False)
        if probe.returncode == 0:
            break
        time.sleep(2)
    else:
        raise TimeoutError("Owned pool did not recover; preserve evidence")
    nested("start", "gitea")
    docker("start", RUNNER)
    after_parent = json.loads(docker("inspect", PARENT, text=True).stdout)[0]
    assert after_parent["Id"] == parent["Id"] and after_parent["State"]["StartedAt"] != parent["State"]["StartedAt"]
    after_children = json.loads(nested("inspect", "jenkins-parity", "gitea", text=True).stdout)
    assert [c["Id"] for c in children] == [c["Id"] for c in after_children]
    assert not after_children[0]["State"]["Running"] and after_children[1]["State"]["Running"]
    rules = docker("exec", PARENT, "iptables", "-S", "LEROY-POOL-EGRESS", text=True).stdout
    assert "192.168.0.0/16 -j REJECT" in rules and "--dport 8088 -j RETURN" in rules
    assert {tag: json.loads(nested("image", "inspect", tag, text=True).stdout)[0]["Id"] for tag in pool["images"]} == pool["images"]
    after = production_jobs()
    assert after["jobs"] == before["jobs"]
    record = {"at": datetime.now(timezone.utc).isoformat(), "candidate": COMMIT,
              "configuration_encryption_and_hmac_verified": True, "configuration_files_restored": len(expected),
              "jenkins_home_restored_to_separate_volume": True, "jenkins_home_files_verified": len(original_files),
              "jenkins_backup_sha256": hashlib.sha256(home_backup.read_bytes()).hexdigest(),
              "jenkins_backup_hmac_sha256": home_tag, "configuration_hmac_sha256": tag,
              "full_pool_stop_and_start": True, "same_container_and_image_identities": True,
              "isolation_rules_restored": True, "restart_policies": "unless-stopped",
              "production_jobs_unchanged": True, "production_modified": False, "production_cutover": False,
              "cold_host_reboot_tested": False, "post_restart_distributed_job_pending": True,
              "scope": "Owned Docker Desktop test pool; no permanent production worker selected", "passed": True}
    record["excluded_replaceable_jenkins_directories"] = ["workspace", "caches", "war"]
    (folder / "report.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
