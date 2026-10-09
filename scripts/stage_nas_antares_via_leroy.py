"""Prepare an exact Antares source mirror inside the isolated NAS test Gitea."""

import argparse
import ast
import base64
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone

from nas_diagnostic import execute
from nas_ssh import ROOT
from watch_nas_graphato_via_leroy import JENKINS_ID

PROGRAM = r"""
import base64,hashlib,json,os,pathlib,subprocess,sys,tempfile,urllib.request,urllib.error
def docker(*args):return subprocess.check_output(['docker',*args],text=True,timeout=180)
assert json.loads(docker('inspect','jenkins-parity'))[0]['Id']==EXPECTED_ID
gitea=json.loads(docker('inspect','gitea'))[0]
assert gitea['Config']['Labels']['io.leroy.nas-parity']=='true' and not gitea['HostConfig']['PortBindings']
worker=json.loads(docker('inspect',os.environ['HOSTNAME']))[0]
assert worker['Config']['Labels']['io.leroy.run']
(mount,)=[m for m in worker['Mounts'] if m['Destination']=='/work']
assert mount['Type']=='volume' and mount['RW']
directory=pathlib.Path.cwd();assert directory.is_relative_to('/work')
bundle=directory/'candidate.bundle';raw=base64.b64decode(BUNDLE,validate=True)
assert hashlib.sha256(raw).hexdigest()==BUNDLE_SHA
bundle.write_bytes(raw)
repo=directory/'candidate.git'
assert not repo.exists()
clone='''import pathlib,subprocess
def git(*args):return subprocess.check_output(['git',*args],text=True).strip()
assert git('-c','safe.directory=/source','--git-dir=/source','rev-parse','HEAD')==BASE
subprocess.run(['git','-c','safe.directory=/source','clone','--bare','--no-hardlinks','/source',REPO],check=True)
subprocess.run(['git','--git-dir='+REPO,'fetch',BUNDLE,'HEAD'],check=True)
assert git('--git-dir='+REPO,'rev-parse','FETCH_HEAD')==COMMIT
subprocess.run(['git','--git-dir='+REPO,'update-ref','refs/heads/master',COMMIT],check=True)
subprocess.run(['git','--git-dir='+REPO,'symbolic-ref','HEAD','refs/heads/master'],check=True)
'''
prefix='BASE='+repr(BASE)+'\nREPO='+repr(str(repo))+'\nBUNDLE='+repr(str(bundle))+'\nCOMMIT='+repr(COMMIT)+'\n'
docker('run','--rm','--pull=never','--network','none','--memory','256m','--cpus','0.5',
 '--mount','type=volume,source='+mount['Name']+',target=/work',
 '--mount','type=bind,source=/sources/antares-candidate-'+BASE[:12]+',target=/source,readonly',
 '--entrypoint','python3','leroy-job:nas-parity','-c',prefix+clone)
assert subprocess.check_output(['git','--git-dir='+str(repo),'rev-parse','HEAD'],text=True).strip()==COMMIT
headers={'Authorization':'Basic '+base64.b64encode((os.environ['GIT_USER']+':'+os.environ['GIT_PASSWORD']).encode()).decode(),'Content-Type':'application/json'}
endpoint='http://gitea:3000/api/v1/repos/gitea-admin/'+NAME
try:
 with urllib.request.urlopen(urllib.request.Request(endpoint,headers=headers),timeout=20):pass
except urllib.error.HTTPError as error:assert error.code==404
else:raise ValueError('Candidate repository already exists; inspect it before any retry')
data=json.dumps({'name':NAME,'private':False,'auto_init':False,'default_branch':'master','description':'Isolated Leroy/Jenkins candidate '+COMMIT}).encode()
with urllib.request.urlopen(urllib.request.Request('http://gitea:3000/api/v1/user/repos',data=data,headers=headers),timeout=30) as response:
 assert response.status==201
 created=json.load(response)
assert created['full_name']=='gitea-admin/'+NAME and not created['private']
url='http://gitea:3000/gitea-admin/'+NAME+'.git'
with tempfile.TemporaryDirectory(prefix='candidate-auth-') as temporary:
 askpass=pathlib.Path(temporary)/'askpass'
 askpass.write_text('#!'+sys.executable+'\nimport os,sys\nprint(os.environ["GIT_USER"] if "username" in sys.argv[1].lower() else os.environ["GIT_PASSWORD"])\n')
 askpass.chmod(0o700)
 environment={**os.environ,'GIT_ASKPASS':str(askpass),'GIT_TERMINAL_PROMPT':'0'}
 subprocess.run(['git','--git-dir='+str(repo),'push',url,'refs/heads/master'],env=environment,check=True,timeout=180)
anonymous={k:v for k,v in os.environ.items() if not k.startswith(('GIT_','SSH_'))}
anonymous.update(GIT_TERMINAL_PROMPT='0',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null')
assert subprocess.check_output(['git','-c','credential.helper=','ls-remote',url,'refs/heads/master'],env=anonymous,text=True,timeout=30).split()[0]==COMMIT
pathlib.Path('staged-source.json').write_text(json.dumps({'source':url,'commit':COMMIT,'repository_id':created['id'],'anonymous_clone_verified':True,'test_network_only':True}))
print('Exact candidate published only in the existing isolated Gitea; no pipeline started.')
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--checkout", default=str(ROOT / ".sources/antares-nas-validation"))
    parser.add_argument("--local-proof", default="local-linux-browsers-full-four-gib.json")
    args = parser.parse_args()
    checkout = (ROOT / args.checkout).resolve()
    assert checkout.is_relative_to((ROOT / ".sources").resolve())
    assert re.fullmatch(r"local-linux-browsers-[a-z0-9-]+\.json", args.local_proof)

    def git(*args):
        return subprocess.check_output(["git", "-C", str(checkout), *args])

    commit = git("rev-parse", "HEAD").decode().strip()
    base = "e4e47930fc69a3ad8fa46b6668242f9de81338a0"
    assert re.fullmatch("[a-f0-9]{40}", commit) and not git("status", "--porcelain").strip()
    subprocess.run(["git", "-C", str(checkout), "merge-base", "--is-ancestor", base, commit], check=True)
    original = json.loads((ROOT / "test-results/nas-parity/baseline.json").read_text())["sources"]["antares"]["commit"]
    assert git("show", original + ":Jenkinsfile") == git("show", commit + ":Jenkinsfile")
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / commit
    assert not (folder / "staged.json").exists()
    probe = json.loads((folder / args.local_proof).read_text())
    assert probe["commit"] == commit and probe["passed"] and probe["full_matrix_requested"] and not probe["oom_events"]
    bundle = ROOT / ".local/nas-parity" / ("antares-" + commit[:12] + "-incremental.bundle")
    if not bundle.exists():
        subprocess.run(["git", "-C", str(checkout), "bundle", "create", str(bundle), base + "..HEAD"], check=True)
    subprocess.run(["git", "-C", str(checkout), "bundle", "verify", str(bundle)],check=True,capture_output=True)
    patch = ROOT / "docs/upstream-patches" / ("antares-nas-" + commit[:12] + ".patch")
    content = git("diff", "--binary", "--full-index", original, commit)
    if patch.exists():
        assert patch.read_bytes() == content
    else:
        patch.write_bytes(content)
    values = {"EXPECTED_ID": JENKINS_ID, "BASE": base, "COMMIT": commit,
              "NAME": "antares-candidate-" + commit[:12],
              "BUNDLE": base64.b64encode(bundle.read_bytes()).decode(),
              "BUNDLE_SHA": hashlib.sha256(bundle.read_bytes()).hexdigest()}
    program = "\n".join(key + "=" + repr(value) for key, value in values.items()) + "\n" + PROGRAM
    compile(program, "isolated-antares-source", "exec")
    embedded = next(
        node.value.value
        for node in ast.parse(PROGRAM).body
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "clone" for t in node.targets)
    )
    compile(embedded, "isolated-antares-clone", "exec")
    if args.prepare_only:
        print(json.dumps({"candidate": commit, "incremental_bundle_bytes": bundle.stat().st_size, "remote_actions": False}))
        return
    diagnostic, run = execute("antares-source-" + commit[:12], program, secrets=("git",), timeout=420, artifacts=["staged-source.json"])
    record = json.loads((diagnostic / "leroy-artifacts/probe/staged-source.json").read_text())
    record.update(repository="antares", original_commit=original, jenkinsfiles_unchanged=True,
                  application_patches_applied=True, jobs_started=False, at=datetime.now(timezone.utc).isoformat(),
                  bundle_sha256=values["BUNDLE_SHA"], bundle_prerequisite=base, diagnostic_run=run["id"],
                  patch="docs/upstream-patches/antares-nas-" + commit[:12] + ".patch",
                  changes=git("log", "--format=%H %s", original + ".." + commit).decode().splitlines())
    (folder / "staged.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
