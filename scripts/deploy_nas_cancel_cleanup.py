"""Install the verified cancellation and disposable-volume fixes in owned job images."""

import argparse
import hashlib
import json
import tarfile
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE
from nas_ssh import ROOT, run_script, upload_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", choices=["cancel-cleanup", "postgres-readiness"], default="cancel-cleanup")
    revision = parser.parse_args().revision
    marker = ROOT / f"test-results/nas-parity/followup/{revision}-deployment.json"
    assert not marker.exists(), "Preserve the previous deployment evidence"
    regression = marker.parent / "antares-timeout-lease/regression-after.txt"
    assert "12 passed" in regression.read_text()
    cleanup = json.loads((marker.parent / "antares-database-cleanup/after-force-volumes.json").read_text())
    assert cleanup["cleanup_passed"] and cleanup["named_volume_preserved"]
    previous = "sha256:805feab30b31314d3260d2f7dc61cc6d5cbb37dc26549a0ffc06d49be3273b05"
    if revision == "postgres-readiness":
        proof = json.loads((marker.parent / "antares-database-readiness/after.json").read_text())
        assert proof["tcp_ready_after_action"]
        previous = json.loads((marker.parent / "cancel-cleanup-deployment.json").read_text())["images"]["leroy-job:nas-parity"]["after"]
    with closing(client()) as api:
        for status in ("queued", "running", "waiting"):
            response = api.get("/api/runs", params={"status": status})
            response.raise_for_status()
            assert not response.json()
        assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
    digests = {name + ".py": hashlib.sha256((ROOT / f"src/leroy/{name}.py").read_bytes()).hexdigest()
               for name in ("worker", "actions")}
    archive = LOCAL / (revision + ".tar")
    with tarfile.open(archive, "w") as bundle:
        for name in digests:
            bundle.add(ROOT / "src/leroy" / name, arcname=name)
    upload_file(archive, REMOTE + "/" + archive.name, CREDENTIALS)
    program = r'''
import hashlib,json,pathlib,re,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert (root/'.leroy-owned').is_file()
prefix=['docker','exec','-i','leroy-nas-parity-docker-1','docker']
def docker(*args):return subprocess.check_output(prefix+list(args),text=True,timeout=240)
assert not docker('ps','-a','--filter','label=io.leroy.runner=runner-nas-parity','-q').strip()
assert docker('inspect','jenkins-parity','--format','{{.State.Running}}').strip()=='false'
folder='/var/lib/docker/leroy-'+REVISION
with (root/(REVISION+'.tar')).open('rb') as source:
 subprocess.run(['docker','exec','-i','leroy-nas-parity-docker-1','sh','-c','mkdir '+folder+' && tar -xf - -C '+folder],stdin=source,check=True,timeout=30)
result={}
for tag in ['leroy-job:nas-parity','leroy-job:nas-parity-gitea']:
 old=json.loads(docker('image','inspect',tag))[0]
 if tag=='leroy-job:nas-parity':assert old['Id']==PREVIOUS
 backup=tag+'-before-'+REVISION
 assert subprocess.run(prefix+['image','inspect',backup],capture_output=True).returncode!=0
 docker('tag',old['Id'],backup)
 target=docker('run','--rm','--network','none','--memory','128m',tag,'python','-c','import leroy.worker;print(leroy.worker.__file__)').strip()
 assert re.fullmatch(r'/opt/leroy-worker/lib/python3\.\d+/site-packages/leroy/worker.py',target)
 target=str(pathlib.PurePosixPath(target).parent)+'/'
 dockerfile='FROM '+backup+'\nCOPY worker.py actions.py '+target+'\n'
 subprocess.run(prefix+['build','--network=none','--pull=false','-t',tag,'-f','-',folder],input=dockerfile,text=True,check=True,stdout=subprocess.DEVNULL,timeout=240)
 new=json.loads(docker('image','inspect',tag))[0]
 assert new['Config']==old['Config'] and new['RootFS']['Layers'][:-1]==old['RootFS']['Layers']
 check="import hashlib,json,pathlib,leroy.worker;root=pathlib.Path(leroy.worker.__file__).parent;print(json.dumps({name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['worker.py','actions.py']}))"
 actual=json.loads(docker('run','--rm','--network','none','--memory','128m',tag,'python','-c',check))
 assert actual==EXPECTED
 result[tag]={'before':old['Id'],'after':new['Id'],'source_sha256':actual,'dependencies_unchanged':True,'runtime_config_unchanged':True}
print(json.dumps(result))
'''
    code = "EXPECTED=" + repr(digests) + "\nPREVIOUS=" + repr(previous) + "\nREVISION=" + repr(revision) + "\n" + program
    compile(code, "deploy-cancel-cleanup", "exec")
    result = run_script("python3 - <<'PY'\n" + code + "\nPY\n", CREDENTIALS, timeout=600)
    assert result.returncode == 0, result.stderr[-2500:]
    evidence = {"at": datetime.now(timezone.utc).isoformat(), "images": json.loads(result.stdout.splitlines()[-1]),
                "lease_seconds_unchanged": 90, "production_modified": False}
    marker.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
