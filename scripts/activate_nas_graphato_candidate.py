"""Select a staged Graphato candidate exclusively in the isolated test Gitea."""

import argparse
import json
import re
import subprocess
from contextlib import closing

from compare_nas_antares import client, jenkins_python
from nas_followup_support import inner
from nas_ssh import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", default="48b741264f3b8353400649f6b05abf6a9c129233")
    parser.add_argument("--checkout", default=str(ROOT / ".sources/graphato-nas-validation"))
    parser.add_argument("--frozen-production-source", action="store_true",
                        help="Select the separately verified production revision in the owned test Gitea")
    parser.add_argument("--frozen-master-source", action="store_true",
                        help="Select the separately recorded upstream master commit in the owned test Gitea")
    args = parser.parse_args()
    previous = args.previous
    assert re.fullmatch("[a-f0-9]{40}", previous)
    checkout = (ROOT / args.checkout).resolve()
    assert checkout.is_relative_to((ROOT / ".sources").resolve())
    commit = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    folder = ROOT / "test-results/nas-parity/followup/candidates/graphato" / commit
    staged = json.loads((folder / "staged.json").read_text())
    assert not (args.frozen_production_source and args.frozen_master_source)
    frozen_source = args.frozen_production_source or args.frozen_master_source
    if args.frozen_master_source:
        frozen = json.loads((folder / "frozen-master.json").read_text())
        assert staged["source_kind"] == "frozen_master_revision" and frozen["commit"] == commit
        assert not staged["application_patches_applied"] and staged["original_commit"] == commit
        assert frozen["bundle_sha256"] == staged["bundle_sha256"] and frozen["branch"] == "master"
    elif args.frozen_production_source:
        assert staged["source_kind"] == "observed_production_revision"
        assert not staged["application_patches_applied"] and staged["original_commit"] == commit
        reviewed = json.loads((ROOT / "test-results/nas-parity/followup/production-source-review/review.json").read_text())
        assert reviewed["applications"]["graphato"]["production_commit"] == commit
    else:
        subprocess.run(["git", "-C", str(checkout), "merge-base", "--is-ancestor", previous, commit], check=True)
    marker = folder / "activated.json"
    assert not marker.exists(), "Inspect the existing activation before repeating it"
    assert (
        inner("inspect", "gitea", "--format", '{{index .Config.Labels "io.leroy.nas-parity"}}').strip()
        == "true"
    )
    with closing(client()) as api:
        for status in ("running", "waiting", "queued"):
            assert not any(
                r["pipeline_id"].startswith("graphato-")
                for r in api.get("/api/runs", params={"status": status}).json()
            )
        jobs = json.loads(
            jenkins_python(
                "from urllib.request import urlopen\n"
                + """
import base64,json,os,urllib.request
headers={'Authorization':'Basic '+base64.b64encode(('admin:'+os.environ['PARITY_PASSWORD']).encode()).decode()}
with urlopen(urllib.request.Request('http://127.0.0.1:8080/api/json?tree=jobs[name,lastBuild[building]]',headers=headers),timeout=20) as r:print(r.read().decode())
"""
            )
        )
        assert not any(
            j["name"].startswith("graphato-") and j.get("lastBuild", {}).get("building") for j in jobs["jobs"]
        )
        program = r"""
import base64,json,os,pathlib,subprocess,urllib.request,urllib.error
credential=json.load(open('/fixtures/gitea-test-credential.json'))
headers={'Authorization':'Basic '+base64.b64encode((credential['user']+':'+credential['password']).encode()).decode()}
url='http://gitea:3000/gitea-admin/graphato.git'
def head():
 with urllib.request.urlopen(urllib.request.Request('http://gitea:3000/api/v1/repos/gitea-admin/graphato/branches/master',headers=headers),timeout=20) as r:return json.load(r)['commit']['id']
assert head()==PREVIOUS
askpass=pathlib.Path('/tmp/leroy-candidate-askpass.py')
askpass.write_text("#!/usr/bin/python3\nimport json,sys\nc=json.load(open('/fixtures/gitea-test-credential.json'))\nprint(c['user'] if 'username' in sys.argv[1].lower() else c['password'])\n")
askpass.chmod(0o700)
try:
 env={**os.environ,'GIT_ASKPASS':str(askpass),'GIT_TERMINAL_PROMPT':'0'}
 lease=['--force-with-lease=refs/heads/master:'+PREVIOUS] if FROZEN_PRODUCTION_SOURCE else []
 refs=[PREVIOUS+':refs/tags/leroy-parity-before-'+COMMIT[:12],COMMIT+':refs/heads/master']
 if FROZEN_PRODUCTION_SOURCE:
  # The separately frozen production bundle cannot contain unpublished test
  # candidate objects. Preserve the old fixture ref through its own Gitea API.
  tag='leroy-parity-before-'+COMMIT[:12]
  endpoint='http://gitea:3000/api/v1/repos/gitea-admin/graphato/tags'
  try:
   with urllib.request.urlopen(urllib.request.Request(endpoint+'/'+tag,headers=headers),timeout=20) as r:prior=json.load(r)
  except urllib.error.HTTPError as error:
   assert error.code==404
   with urllib.request.urlopen(urllib.request.Request(endpoint,headers={**headers,'Content-Type':'application/json'},
    data=json.dumps({'tag_name':tag,'target':PREVIOUS}).encode()),timeout=20) as r:prior=json.load(r)
  assert (prior['commit'].get('sha') or prior['commit'].get('id'))==PREVIOUS
  refs=[COMMIT+':refs/heads/master']
 subprocess.run(['git','-c','safe.directory='+SOURCE,'--git-dir='+SOURCE,'push',*lease,url,
  *refs],env=env,check=True,capture_output=True,timeout=120)
 assert head()==COMMIT
 print(json.dumps({'before':PREVIOUS,'after':COMMIT,'production_git_changed':False}))
finally:askpass.unlink()
"""
        report = json.loads(
            jenkins_python(
                "PREVIOUS="
                + repr(previous)
                + "\nCOMMIT="
                + repr(commit)
                + "\nSOURCE="
                + repr(staged["source"])
                + "\n"
                + "FROZEN_PRODUCTION_SOURCE=" + repr(frozen_source) + "\n"
                + program,
                timeout=180,
            )
        )
        specs = api.get("/api/pipelines").json()
        assert not any(p["enabled"] for p in specs)
        before = {}
        for row in specs:
            if not row["id"].startswith("graphato-"):
                continue
            spec = row["spec"]
            before[row["id"]] = json.loads(json.dumps(spec))
            if row["id"] != "graphato-bootstrap-host":
                spec["source"]["commit"] = commit
                spec["source"]["application_patches_applied"] = staged["application_patches_applied"]
            for param in spec["parameters"]:
                if param["name"] in ("GRAPHATO_REF", "RELEASE_COMMIT"):
                    param["default"] = commit
            api.put("/api/pipelines/" + row["id"], json=spec).raise_for_status()
        (folder / "leroy-before.json").write_text(json.dumps(before, indent=2) + "\n")
        for pipeline in before:
            output = folder / pipeline
            output.mkdir(exist_ok=True)
            prepared = json.loads(
                (ROOT / "test-results/nas-parity/aligned" / pipeline / "prepared.json").read_text()
            )
            for name in ("GRAPHATO_REF", "RELEASE_COMMIT"):
                if name in prepared["parameters"]:
                    prepared["parameters"][name] = commit
            if pipeline == "graphato-bootstrap-host":
                prepared["parameters"]["GRAPHATO_REF"] = commit
            (output / "prepared.json").write_text(json.dumps(prepared, indent=2) + "\n")
        marker.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
