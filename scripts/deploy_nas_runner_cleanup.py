"""Install nested-container recovery only in the idle, owned NAS supervisor."""

import hashlib
import json
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from deploy_nas_parity import CREDENTIALS, REMOTE
from nas_ssh import ROOT, run_script, upload_file


def main():
    folder = ROOT / "test-results/nas-parity/followup/runner-nested-cleanup"
    marker = folder / "deployment.json"
    assert not marker.exists()
    assert json.loads((folder / "local.json").read_text())["passed"]
    with closing(client()) as api:
        for status in ("running", "queued", "waiting"):
            response = api.get("/api/runs", params={"status": status})
            response.raise_for_status()
            assert not response.json()
        assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
    path = ROOT / "src/leroy/runner.py"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    upload_file(path, REMOTE + "/runner-nested-cleanup.py", CREDENTIALS)
    previous = json.loads((ROOT / "test-results/nas-parity/lease-fix-deployment.json").read_text())["images"]["leroy-runner:nas-parity"]["after"]
    program = r'''
import hashlib,json,pathlib,re,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert (root/'.leroy-owned').is_file()
def docker(*args):return subprocess.check_output(['docker',*args],text=True,timeout=240)
assert not docker('exec','leroy-nas-parity-docker-1','docker','ps','-a','--filter','label=io.leroy.runner=runner-nas-parity','-q').strip()
info=json.loads(docker('inspect','leroy-nas-parity-runner-1'))[0]
assert info['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
assert info['Config']['Labels']['com.docker.compose.service']=='runner'
old=json.loads(docker('image','inspect',info['Image']))[0]
assert old['Id']==PREVIOUS
backup='leroy-runner:nas-parity-before-nested-cleanup'
assert subprocess.run(['docker','image','inspect',backup],capture_output=True).returncode!=0
docker('tag',old['Id'],backup)
destination=docker('exec','leroy-nas-parity-runner-1','python','-c','import leroy.runner;print(leroy.runner.__file__)').strip()
assert re.fullmatch(r'/usr/local/lib/python3\.\d+/site-packages/leroy/runner.py',destination)
folder=root/'runner-nested-cleanup';folder.mkdir()
source=(root/'runner-nested-cleanup.py').read_bytes();assert hashlib.sha256(source).hexdigest()==EXPECTED
(folder/'runner.py').write_bytes(source)
(folder/'Dockerfile').write_text('FROM '+backup+'\nCOPY runner.py '+destination+'\n')
docker('build','--network=none','--pull=false','-t','leroy-runner:nas-parity',str(folder))
new=json.loads(docker('image','inspect','leroy-runner:nas-parity'))[0]
assert new['Config']==old['Config'] and new['RootFS']['Layers'][:-1]==old['RootFS']['Layers']
subprocess.run(['docker','compose','up','-d','--no-deps','runner'],cwd=root,check=True,timeout=90)
assert json.loads(docker('inspect','leroy-nas-parity-runner-1'))[0]['Image']==new['Id']
actual=docker('exec','leroy-nas-parity-runner-1','python','-c','import hashlib,leroy.runner;print(hashlib.sha256(open(leroy.runner.__file__,"rb").read()).hexdigest())').strip()
assert actual==EXPECTED
print(json.dumps({'previous_image':old['Id'],'image':new['Id'],'source_sha256':actual,'dependencies_unchanged':True,'runtime_config_unchanged':True}))
'''
    code = "EXPECTED=" + repr(digest) + "\nPREVIOUS=" + repr(previous) + "\n" + program
    compile(code, "runner-cleanup-deployment", "exec")
    result = run_script("python3 - <<'PY'\n" + code + "\nPY\n", CREDENTIALS, timeout=420)
    assert result.returncode == 0, result.stderr[-2000:]
    evidence = json.loads(result.stdout.splitlines()[-1])
    evidence.update(at=datetime.now(timezone.utc).isoformat(), production_modified=False)
    marker.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
