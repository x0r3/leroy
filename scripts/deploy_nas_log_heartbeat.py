"""Deploy the verified log-lock correction to the idle owned NAS controller."""

import hashlib
import json
import tarfile
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE
from nas_ssh import ROOT, run_script, upload_file


def main():
    marker = ROOT / "test-results/nas-parity/followup/log-heartbeat-deployment.json"
    assert not marker.exists(), "Inspect the recorded deployment instead of repeating it"
    proof = json.loads((marker.parent / "log-heartbeat-tests.json").read_text())
    assert proof["passed"] and proof["postgresql_real"] and proof["tests"] >= 65
    digests = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
               for name in proof["source_sha256"]}
    assert digests == proof["source_sha256"]
    assert set(digests) == {"src/leroy/" + name + ".py" for name in ("api", "db", "maintenance")}
    with closing(client()) as api:
        for status in ("queued", "running", "waiting"):
            response = api.get("/api/runs", params={"status": status})
            response.raise_for_status()
            assert not response.json()
        assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
    archive = LOCAL / "log-heartbeat.tar"
    with tarfile.open(archive, "w") as bundle:
        for name in digests:
            bundle.add(ROOT / name, arcname=name.rsplit("/", 1)[1])
    upload_file(archive, REMOTE + "/" + archive.name, CREDENTIALS)
    program = r'''
import hashlib,json,pathlib,re,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert (root/'.leroy-owned').is_file()
def docker(*args):return subprocess.check_output(['docker',*args],text=True,timeout=240)
info=json.loads(docker('inspect','leroy-nas-parity-controller-1'))[0]
assert info['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
assert info['Config']['Labels']['com.docker.compose.service']=='controller'
before=json.loads(docker('image','inspect',info['Image']))[0]
assert before['Id']==PREVIOUS
destination=docker('exec','leroy-nas-parity-controller-1','python','-c','import leroy.api;print(leroy.api.__file__)').strip()
assert re.fullmatch(r'/usr/local/lib/python3\.\d+/site-packages/leroy/api.py',destination)
destination=str(pathlib.PurePosixPath(destination).parent)+'/'
backup='leroy-controller:nas-parity-before-log-heartbeat'
assert subprocess.run(['docker','image','inspect',backup],capture_output=True).returncode!=0
docker('tag',before['Id'],backup)
folder=root/'log-heartbeat';folder.mkdir()
subprocess.run(['tar','-xf',str(root/'log-heartbeat.tar'),'-C',str(folder)],check=True)
for name,digest in EXPECTED.items():assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest
(folder/'Dockerfile').write_text('FROM '+backup+'\nCOPY api.py db.py maintenance.py '+destination+'\n')
docker('build','--network=none','--pull=false','-t','leroy-controller:nas-parity',str(folder))
after=json.loads(docker('image','inspect','leroy-controller:nas-parity'))[0]
assert before['Config']==after['Config'] and before['RootFS']['Layers']==after['RootFS']['Layers'][:-1]
subprocess.run(['docker','compose','up','-d','--no-deps','--wait','--wait-timeout','180','controller'],cwd=root,check=True,timeout=210)
assert json.loads(docker('inspect','leroy-nas-parity-controller-1'))[0]['Image']==after['Id']
check="import hashlib,json,pathlib,leroy.api;root=pathlib.Path(leroy.api.__file__).parent;print(json.dumps({name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['api.py','db.py','maintenance.py']}))"
actual=json.loads(docker('exec','leroy-nas-parity-controller-1','python','-c',check))
assert actual==EXPECTED
print(json.dumps({'previous_image':before['Id'],'image':after['Id'],'source_sha256':actual,'dependencies_unchanged':True,'runtime_config_unchanged':True,'lease_seconds_unchanged':90}))
'''
    previous = json.loads((marker.parent / "artifact-concurrency-deployment.json").read_text())
    values = {"EXPECTED": {name.rsplit("/", 1)[1]: digest for name, digest in digests.items()},
              "PREVIOUS": previous["image"]}
    code = "\n".join(key + "=" + repr(value) for key, value in values.items()) + "\n" + program
    compile(code, "nas-log-heartbeat", "exec")
    result = run_script("python3 - <<'PY'\n" + code + "\nPY\n", CREDENTIALS, timeout=600)
    assert result.returncode == 0, result.stderr[-2500:]
    evidence = json.loads(result.stdout.splitlines()[-1])
    with closing(client()) as api:
        api.get("/health/ready").raise_for_status()
        assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
        for name, digest in previous["served_assets"].items():
            response = api.get("/" if name == "index.html" else "/" + name)
            response.raise_for_status()
            assert hashlib.sha256(response.content).hexdigest() == digest
    evidence.update(at=datetime.now(timezone.utc).isoformat(), readiness=True,
                    ui_assets_unchanged=True, production_modified=False)
    marker.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
