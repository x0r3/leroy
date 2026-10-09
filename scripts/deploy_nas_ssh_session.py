"""Install the tested SSH adapter in the two owned NAS job images only."""

import hashlib
import json
import tarfile
from contextlib import closing

from compare_nas_antares import client
from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE
from nas_ssh import ROOT, run_script, upload_file


def main():
    output = ROOT / "test-results/nas-parity/followup/ssh-session-deployment.json"
    assert not output.exists(), "Deployment already recorded"
    proof = json.loads((output.parent / "ssh-session-v3/run.json").read_text())
    assert proof["status"] == "succeeded"
    with closing(client()) as api:
        for status in ("queued", "running", "waiting"):
            response = api.get("/api/runs", params={"status": status})
            response.raise_for_status()
            assert not response.json()
    archive = LOCAL / "ssh-session-fix.tar"
    with tarfile.open(archive, "w") as bundle:
        for name in ("actions", "ssh_session"):
            bundle.add(ROOT / f"src/leroy/{name}.py", name + ".py")
    upload_file(archive, REMOTE + "/ssh-session-fix.tar", CREDENTIALS)
    program = r"""
import hashlib,json,pathlib,subprocess,tarfile
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert (root/'.leroy-owned').is_file()
prefix=['docker','exec','-i','leroy-nas-parity-docker-1','docker']
context='/var/lib/docker/leroy-ssh-session-fix'
with (root/'ssh-session-fix.tar').open('rb') as source:
 subprocess.run(['docker','exec','-i','leroy-nas-parity-docker-1','sh','-c','mkdir -p '+context+' && tar -xf - -C '+context],stdin=source,check=True,timeout=60)
with tarfile.open(root/'ssh-session-fix.tar') as archive:
 hashes={n:hashlib.sha256(archive.extractfile(n+'.py').read()).hexdigest() for n in ['actions','ssh_session']}
images={}
for name in ['leroy-job:nas-parity','leroy-job:nas-parity-gitea']:
 old=json.loads(subprocess.check_output(prefix+['image','inspect',name],timeout=60))[0]
 backup=name+'-before-ssh-session'
 assert subprocess.run(prefix+['image','inspect',backup],capture_output=True,timeout=60).returncode!=0
 subprocess.run(prefix+['tag',old['Id'],backup],check=True,timeout=60)
 dockerfile=f'FROM {backup}\nCOPY actions.py ssh_session.py /opt/leroy-worker/lib/python3.13/site-packages/leroy/\n'
 subprocess.run(prefix+['build','--network=none','--pull=false','-t',name,'-f','-',context],input=dockerfile,text=True,check=True,stdout=subprocess.DEVNULL,timeout=180)
 new=json.loads(subprocess.check_output(prefix+['image','inspect',name],timeout=60))[0]
 assert new['Config']==old['Config'] and new['RootFS']['Layers'][:-1]==old['RootFS']['Layers']
 check="import hashlib,json,leroy.actions,leroy.ssh_session;print(json.dumps({n:hashlib.sha256(open(getattr(leroy,n).__file__,'rb').read()).hexdigest() for n in ['actions','ssh_session']}))"
 actual=json.loads(subprocess.check_output(prefix+['run','--rm','--network','none','--memory','128m',name,'python','-c',check],text=True,timeout=60))
 assert actual==hashes
 images[name]={'before':old['Id'],'after':new['Id'],'dependencies_unchanged':True}
print(json.dumps({'images':images,'source_hashes':hashes,'application_sources_changed':False}))
"""
    result = run_script("python3 - <<'PY'\n" + program + "PY\n", CREDENTIALS, timeout=600)
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    report = json.loads(result.stdout)
    assert report["source_hashes"] == {
        name: hashlib.sha256((ROOT / f"src/leroy/{name}.py").read_bytes()).hexdigest()
        for name in ("actions", "ssh_session")
    }
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
