"""Stage separately reviewed application commits in the owned NAS source store."""

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone

from nas_followup_support import remote
from nas_ssh import ROOT, upload_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", choices=["antares", "graphato"])
    name = parser.parse_args().repository
    checkout = ROOT / (".sources/" + name + "-nas-validation")

    def git(*args):
        return subprocess.check_output(["git", "-C", str(checkout), *args])

    baseline = json.loads((ROOT / "test-results/nas-parity/baseline.json").read_text())
    original = baseline["sources"][name]["commit"]
    commit = git("rev-parse", "HEAD").decode().strip()
    assert not git("status", "--porcelain").strip(), "Commit the reviewed candidate first"
    subprocess.run(["git", "-C", str(checkout), "merge-base", "--is-ancestor", original, commit], check=True)
    jobs = [j for j in baseline["pipelines"] if j["repository"] == name]
    for job in jobs:
        assert git("show", original + ":" + job["script_path"]) == git(
            "show", commit + ":" + job["script_path"]
        )
    folder = ROOT / "test-results/nas-parity/followup/candidates" / name / commit
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / "staged.json"
    if marker.exists():
        print(marker.read_text())
        return
    bundle = ROOT / ".local/nas-parity" / (name + "-" + commit[:12] + ".bundle")
    subprocess.run(["git", "-C", str(checkout), "bundle", "create", str(bundle), "HEAD"], check=True)
    patch = ROOT / "docs/upstream-patches" / (name + "-nas-" + commit[:12] + ".patch")
    patch.write_bytes(git("format-patch", "--stdout", original + ".." + commit))
    remote_bundle = "/volume1/docker/leroy-nas-parity/" + bundle.name
    upload_file(bundle, remote_bundle, ROOT / ".local/nas-ssh.json")
    target = name + "-candidate-" + commit[:12]
    program = r"""
import hashlib,json,pathlib,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert (root/'.leroy-owned').is_file()
assert hashlib.sha256((root/BUNDLE).read_bytes()).hexdigest()==SHA
assert not (root/'sources'/TARGET).exists(), 'Inspect an existing candidate before resuming staging'
args=['docker','run','--rm','--network','none','--memory','256m','--cpus','0.5',
 '-v',str(root/'sources')+':/sources','-v',str(root)+':/input:ro',
 '--entrypoint','python3','leroy-job:nas-parity','-c',
 'import subprocess; subprocess.run(["git","clone","--bare","/input/'+BUNDLE+'","/sources/'+TARGET+'"],check=True); subprocess.run(["git","--git-dir=/sources/'+TARGET+'","update-ref","refs/heads/master","'+COMMIT+'"],check=True); subprocess.run(["git","--git-dir=/sources/'+TARGET+'","symbolic-ref","HEAD","refs/heads/master"],check=True)']
subprocess.run(args,check=True,capture_output=True,timeout=240)
print(json.dumps({'source':'/sources/'+TARGET,'commit':COMMIT,'jenkinsfiles_unchanged':True}))
"""
    identity = {
        "BUNDLE": bundle.name,
        "SHA": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "TARGET": target,
        "COMMIT": commit,
    }
    report = json.loads(
        remote("\n".join(k + "=" + repr(v) for k, v in identity.items()) + "\n" + program, timeout=300)
    )
    report.update(
        repository=name,
        original_commit=original,
        at=datetime.now(timezone.utc).isoformat(),
        bundle_sha256=identity["SHA"],
        patch=str(patch.relative_to(ROOT)).replace("\\", "/"),
        application_patches_applied=True,
        jobs_started=False,
        changes=git("log", "--format=%H %s", original + ".." + commit).decode().splitlines(),
    )
    marker.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
