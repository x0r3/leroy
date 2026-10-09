"""Stage the observed production commit without changing production or old sources."""

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone

from nas_followup_support import remote
from nas_ssh import ROOT, upload_file

COMMIT = os.environ.get("LEROY_NAS_FROZEN_GRAPHATO_COMMIT", "ed21c2e6346aab6f71494765a37ba91e0d4559b7")
assert re.fullmatch(r"[a-f0-9]{40}", COMMIT)


def main():
    review = json.loads((ROOT / "test-results/nas-parity/followup/production-source-review/review.json").read_text())
    assert review["applications"]["graphato"]["production_commit"] == COMMIT
    checkout = ROOT / ".sources/production-review/graphato-ed21c2e6346a"
    assert subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip() == COMMIT
    assert not subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain"]).strip()
    folder = ROOT / "test-results/nas-parity/followup/candidates/graphato" / COMMIT
    folder.mkdir(exist_ok=True)
    marker = folder / "staged.json"
    assert not marker.exists(), "Do not overwrite existing source evidence"
    bundle = ROOT / ".local/nas-parity" / ("graphato-production-" + COMMIT[:12] + ".bundle")
    assert not bundle.exists()
    subprocess.run(["git", "-C", str(checkout), "bundle", "create", str(bundle), "HEAD"], check=True, capture_output=True)
    sha = hashlib.sha256(bundle.read_bytes()).hexdigest()
    upload_file(bundle, "/volume1/docker/leroy-nas-parity/" + bundle.name, ROOT / ".local/nas-ssh.json")
    target = "graphato-production-" + COMMIT[:12]
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
print(json.dumps({'source':'/sources/'+TARGET,'production_modified':False}))
'''
    result = json.loads(remote("BUNDLE=" + repr(bundle.name) + "\nSHA=" + repr(sha)
                               + "\nTARGET=" + repr(target) + "\n" + program, timeout=270))
    result.update(repository="graphato", commit=COMMIT, original_commit=COMMIT,
                  at=datetime.now(timezone.utc).isoformat(), bundle_sha256=sha, patch=None,
                  application_patches_applied=False, jenkinsfiles_unchanged=True,
                  jobs_started=False, source_kind="observed_production_revision",
                  production_inventory=review["inventory_evidence"])
    marker.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
