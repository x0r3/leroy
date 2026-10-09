"""Freeze an explicitly observed upstream master without changing either upstream."""

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone

from nas_followup_support import remote
from nas_ssh import ROOT, upload_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    commit = args.commit
    assert re.fullmatch(r"[a-f0-9]{40}", commit)
    repository = ROOT.parent / "graphato"

    def git(*arguments):
        return subprocess.check_output(["git", "-C", str(repository), *arguments])

    upstream = git("remote", "get-url", "origin").decode().strip()
    assert upstream == "https://github.com/x0r3/graphato"
    observed = git("ls-remote", "origin", "refs/heads/master").decode().strip().split()
    assert observed == [commit, "refs/heads/master"], "Upstream moved; review the newly observed commit explicitly"
    observed_at = datetime.now(timezone.utc).isoformat()
    assert git("rev-parse", "master").decode().strip() == commit
    folder = ROOT / "test-results/nas-parity/followup/candidates/graphato" / commit
    folder.mkdir(parents=True, exist_ok=True)
    assert not (folder / "frozen-master.json").exists(), "Retain the already frozen source record"
    baseline = json.loads((ROOT / "test-results/nas-parity/baseline.json").read_text())
    scripts = {}
    for row in baseline["pipelines"]:
        if row["repository"] != "graphato":
            continue
        digest = hashlib.sha256(git("show", commit + ":" + row["script_path"])).hexdigest()
        assert digest == row["script_sha256"], "Review changed Jenkinsfile before reusing its migration"
        scripts[row["script_path"]] = digest
    checkout = ROOT / ".sources/frozen-master" / ("graphato-" + commit[:12])
    assert not checkout.exists()
    checkout.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--shared", "--no-checkout", str(repository), str(checkout)],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(checkout), "checkout", "--detach", commit], check=True, capture_output=True)
    assert not subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain"]).strip()
    bundle = ROOT / ".local/nas-parity" / ("graphato-master-" + commit[:12] + ".bundle")
    assert not bundle.exists()
    subprocess.run(["git", "-C", str(checkout), "bundle", "create", str(bundle), "HEAD"],
                   check=True, capture_output=True)
    sha = hashlib.sha256(bundle.read_bytes()).hexdigest()
    upload_file(bundle, "/volume1/docker/leroy-nas-parity/" + bundle.name, ROOT / ".local/nas-ssh.json")
    target = "graphato-master-" + commit[:12]
    program = r'''
import hashlib,json,pathlib,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert (root/'.leroy-owned').is_file()
assert hashlib.sha256((root/BUNDLE).read_bytes()).hexdigest()==SHA
assert not (root/'sources'/TARGET).exists()
subprocess.run(['docker','run','--rm','--network','none','--memory','256m','--cpus','0.5',
 '--label','io.leroy.nas-parity=true','-v',str(root/'sources')+':/sources','-v',str(root)+':/input:ro',
 '--entrypoint','git','leroy-job:nas-parity','clone','--bare','/input/'+BUNDLE,'/sources/'+TARGET],
 check=True,capture_output=True,timeout=240)
actual=subprocess.check_output(['docker','run','--rm','--network','none','--memory','128m','--cpus','0.5',
 '-v',str(root/'sources'/TARGET)+':/source:ro','--entrypoint','git','leroy-job:nas-parity',
 '-c','safe.directory=/source','--git-dir=/source','rev-parse','HEAD'],text=True,timeout=60).strip()
assert actual==COMMIT
print(json.dumps({'source':'/sources/'+TARGET,'remote_commit_verified':actual,'production_modified':False}))
'''
    staged = json.loads(remote("BUNDLE=" + repr(bundle.name) + "\nSHA=" + repr(sha)
                               + "\nTARGET=" + repr(target) + "\nCOMMIT=" + repr(commit) + "\n" + program,
                               timeout=330))
    frozen = {"commit": commit, "branch": "master", "upstream": upstream,
              "observed_at": observed_at, "tree": git("rev-parse", commit + "^{tree}").decode().strip(),
              "checkout": checkout.relative_to(ROOT).as_posix(), "bundle_sha256": sha,
              "jenkinsfiles_sha256": scripts, "application_patches_applied": False,
              "upstream_modified": False, "scope": "Master at the recorded observation; later commits do not change this comparison"}
    (folder / "frozen-master.json").write_text(json.dumps(frozen, indent=2) + "\n")
    staged.update(repository="graphato", commit=commit, original_commit=commit,
                  at=observed_at, bundle_sha256=sha, patch=None, application_patches_applied=False,
                  jenkinsfiles_unchanged=True, jobs_started=False, source_kind="frozen_master_revision",
                  source_observation=(folder / "frozen-master.json").relative_to(ROOT).as_posix())
    (folder / "staged.json").write_text(json.dumps(staged, indent=2) + "\n")
    print(json.dumps({"commit": commit, "tree": frozen["tree"], "source": staged["source"],
                      "application_patches_applied": False, "production_modified": False}), flush=True)


if __name__ == "__main__":
    main()
