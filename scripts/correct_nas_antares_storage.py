"""Preserve Jenkins #12 and remove the insufficient database RAM mount."""

import argparse
import base64
import hashlib
import json
import shutil
from datetime import datetime, timezone

from configure_nas_antares_tmpfs import CANDIDATE, PROBE, SOURCE, TARGET
from nas_followup_support import inner, remote, wait_production_jobs
from nas_gitea_target import idle
from nas_ssh import ROOT, upload_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume-verification", action="store_true", help="Verify the already installed policy without reapplying it")
    args = parser.parse_args()
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / CANDIDATE
    marker = folder / "database-storage-corrected.json"
    assert not marker.exists(), "No implicit infrastructure correction"
    state = json.loads((folder / "comparison.json").read_text())
    old = json.loads((folder / "tmpfs-policy-applied.json").read_text())
    assert state["jenkins"]["number"] == 12 and state["jenkins"]["result"] == "FAILURE"
    assert not state["jenkins"]["building"] and state["jenkins_restored"]["stopped"]
    assert not state.get("leroy_run"), "Do not replace a paired pipeline comparison"
    assert "No space left on device" in (folder / "jenkins-console.log").read_text()
    assert old["database_tmpfs"].endswith("size=1g")
    before_jobs = wait_production_jobs()
    idle()
    assert not any(n.startswith("antares-") for n in inner("ps", "--format", "{{.Names}}").splitlines())
    source = ROOT / "infra/nas/antares-docker.py"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    archive = folder / "attempts/database-tmpfs-1g"
    archive.mkdir(parents=True, exist_ok=args.resume_verification)
    paths = sorted({folder / "comparison.json", folder / "tmpfs-policy-applied.json", *folder.glob("jenkins-*")})
    rows = []
    for path in paths:
        assert path.is_file() and path.resolve().is_relative_to(folder.resolve())
        if args.resume_verification:
            assert (archive / path.name).read_bytes() == path.read_bytes()
        else:
            shutil.copy2(path, archive / path.name)
        rows.append({"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    old_source = base64.b64decode(remote(
        "import base64,hashlib,pathlib\n"
        "p=pathlib.Path('/volume1/docker/leroy-nas-parity/fixtures/" + (
            "antares-docker-before-database-storage-correction.py" if args.resume_verification else "antares-docker.py"
        ) + "')\n"
        f"assert hashlib.sha256(p.read_bytes()).hexdigest()=={old['policy_sha256']!r}\n"
        "print(base64.b64encode(p.read_bytes()).decode())\n"
    ).strip())
    assert hashlib.sha256(old_source).hexdigest() == old["policy_sha256"]
    if args.resume_verification:
        assert (archive / "antares-docker.py").read_bytes() == old_source
    else:
        (archive / "antares-docker.py").write_bytes(old_source)
    proof = ROOT / "test-results/nas-parity/followup/antares-tmpfs-policy-tests.json"
    if args.resume_verification:
        assert (archive / proof.name).read_bytes() == proof.read_bytes()
    else:
        shutil.copy2(proof, archive / proof.name)
        upload_file(source, "/volume1/docker/leroy-nas-parity/fixtures/antares-docker-browser-tmpfs.py", ROOT / ".local/nas-ssh.json")
    apply = r'''
import hashlib,pathlib,shutil
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
path=root/'fixtures/antares-docker.py';staged=root/'fixtures/antares-docker-browser-tmpfs.py'
assert hashlib.sha256(path.read_bytes()).hexdigest()==BEFORE
assert hashlib.sha256(staged.read_bytes()).hexdigest()==AFTER
backup=root/'fixtures/antares-docker-before-database-storage-correction.py';assert not backup.exists()
shutil.copy2(path,backup);shutil.copyfile(staged,path);path.chmod(0o755)
print('Owned browser temporary storage policy installed; database remains on disk.')
'''
    if args.resume_verification:
        remote("import hashlib,pathlib\np=pathlib.Path('/volume1/docker/leroy-nas-parity/fixtures/antares-docker.py')\n"
               f"assert hashlib.sha256(p.read_bytes()).hexdigest()=={digest!r}\n")
    else:
        print(remote(f"BEFORE={old['policy_sha256']!r}\nAFTER={digest!r}\n" + apply).strip(), flush=True)
    probe = PROBE.replace(
        "assert info['HostConfig']['Tmpfs']=={'/var/lib/postgresql':'rw,nosuid,nodev,size=1g'}\n assert not [m for m in info['Mounts'] if m['Type']=='volume']",
        "assert not info['HostConfig'].get('Tmpfs')\n volumes=[m for m in info['Mounts'] if m['Type']=='volume']\n assert len(volumes)==1 and volumes[0]['Destination']=='/var/lib/postgresql'",
    )
    assert probe != PROBE
    probe = probe.replace("result={'tmpfs':", "result={'database_storage':'disk','tmpfs':")
    probe = probe.replace("info['HostConfig']['Tmpfs']", "info['HostConfig'].get('Tmpfs',{})")
    # This infrastructure probe must tolerate a cold disk after host pressure.
    # It does not change the application's PostgreSQL health/test deadlines.
    probe = probe.replace("for _ in range(30):", "for _ in range(120):")
    compile(probe, "disk-database-probe", "exec")
    prefix = f"TARGET={TARGET!r}\n"
    # This filesystem/CLI probe needs no Jenkins API or running build.
    inner("start", "jenkins-parity")
    try:
        installed = inner("exec", "jenkins-parity", "python3", "-c",
                          "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('/usr/local/bin/docker').read_bytes()).hexdigest())").strip()
        assert installed == digest
        probes = {"jenkins": json.loads(inner("exec", "-e", "LEROY_NAS_ANTARES_TMPFS=1",
                                               "jenkins-parity", "python3", "-c", prefix + probe, timeout=180))}
        mount = "type=bind,source=" + SOURCE + ",target=" + TARGET + ",readonly"
        probes["leroy"] = json.loads(inner(
            "run", "--rm", "--network", "none", "--memory", "128m", "--cpus", "0.5",
            "--mount", mount, "--mount", "type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock",
            "-e", "LEROY_NAS_ANTARES_TMPFS=1", "leroy-job:nas-parity",
            "python", "-c", prefix + probe, timeout=180))
        assert probes["jenkins"] == probes["leroy"]
    finally:
        inner("stop", "--time", "120", "jenkins-parity", timeout=150)
    after_jobs = wait_production_jobs()
    assert before_jobs["jobs"] == after_jobs["jobs"]
    reason = "Jenkins #12 exhausted the 1-GiB PostgreSQL data/WAL mount during integration tests. Keep the original disk database and only place browser temporary profiles in RAM; no test or application changes."
    record = {
        **old, "at": datetime.now(timezone.utc).isoformat(), "policy_sha256": digest,
        "installed": {"source_sha256": digest, "docker_cli": TARGET}, "engines": probes,
        "database_tmpfs": None, "database_storage": "disk", "previous_policy": "attempts/database-tmpfs-1g/tmpfs-policy-applied.json",
        "diagnostic_only_reason": reason, "production_jobs_unchanged": True,
    }
    (archive / "retry.json").write_text(json.dumps({
        "at": record["at"], "reason": reason, "files": rows,
        "failed_jenkins_build": 12, "leroy_pipeline_started": False,
        "preflight_reused_old_receipt": state["leroy_resource_probe"]["run"],
        "previous_runs_retained": True, "candidate_unchanged": CANDIDATE,
        "full_ci_acceptance": False,
    }, indent=2) + "\n")
    (folder / "tmpfs-policy-applied.json").write_text(json.dumps(record, indent=2) + "\n")
    for path in paths:
        if path.name != "tmpfs-policy-applied.json":
            assert hashlib.sha256(path.read_bytes()).hexdigest() == next(row["sha256"] for row in rows if row["name"] == path.name)
            path.unlink()  # Exact copied evidence files only; archive was verified above.
    marker.write_text(json.dumps(record, indent=2) + "\n")
    proof.write_text(json.dumps({"passed": True, "tests": 13, "sha256": digest,
                                "command": ".venv/Scripts/python.exe -m pytest tests/test_nas_temporary_storage.py -q"}, indent=2) + "\n")
    print(json.dumps({"candidate": CANDIDATE, "same_policy_both": True,
                      "database_storage": "disk", "durability_verified": True,
                      "helpers_removed": True, "production_modified": False,
                      "failed_attempt_retained": True, "full_ci_acceptance": False}), flush=True)


if __name__ == "__main__":
    main()
