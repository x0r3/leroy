"""Install the verified artifact concurrency and graph focus fixes in the idle NAS test controller."""

import hashlib
import json
import tarfile
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE
from nas_ssh import ROOT, run_script, upload_file


def main():
    marker = ROOT / "test-results/nas-parity/followup/artifact-concurrency-deployment.json"
    assert not marker.exists(), "Deployment already recorded"
    proof = json.loads((marker.parent / "artifact-concurrency-tests.json").read_text())
    digest = hashlib.sha256((ROOT / "src/leroy/api.py").read_bytes()).hexdigest()
    assert proof["passed"] and proof["api_sha256"] == digest
    ui = json.loads((ROOT / "test-results/nas-parity/visual-graph-focus-production/report.json").read_text())
    assert ui["passed"] and ui["manual_visual_review"]
    assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value
               for name, value in ui["source_sha256"].items())
    assets = {path.relative_to(ROOT / "web/dist").as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in (ROOT / "web/dist").rglob("*") if path.is_file()}
    assert assets == ui["assets"]
    with closing(client()) as api:
        for status in ("queued", "running", "waiting"):
            response = api.get("/api/runs", params={"status": status})
            response.raise_for_status()
            assert not response.json(), "Wait for the active NAS comparison"
        assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
    archive = LOCAL / "artifact-concurrency.tar"
    with tarfile.open(archive, "w") as bundle:
        bundle.add(ROOT / "src/leroy/api.py", "api.py")
        bundle.add(ROOT / "web/dist", "dist")
    upload_file(archive, REMOTE + "/" + archive.name, CREDENTIALS)
    program = r"""
import hashlib,json,pathlib,re,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert (root/'.leroy-owned').is_file()
def docker(*args):return subprocess.check_output(['docker',*args],text=True,timeout=180)
info=json.loads(docker('inspect','leroy-nas-parity-controller-1'))[0]
assert info['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
assert info['Config']['Labels']['com.docker.compose.service']=='controller'
before=json.loads(docker('image','inspect',info['Image']))[0]
destination=docker('exec','leroy-nas-parity-controller-1','python','-c','import leroy.api;print(leroy.api.__file__)').strip()
assert re.fullmatch(r'/usr/local/lib/python3\.\d+/site-packages/leroy/api.py',destination)
backup='leroy-controller:nas-parity-before-artifact-concurrency'
assert subprocess.run(['docker','image','inspect',backup],capture_output=True).returncode!=0
docker('tag',info['Image'],backup)
folder=root/'artifact-concurrency';folder.mkdir()
subprocess.run(['tar','-xf',str(root/'artifact-concurrency.tar'),'-C',str(folder)],check=True)
assert hashlib.sha256((folder/'api.py').read_bytes()).hexdigest()==EXPECTED
(folder/'Dockerfile').write_text('FROM '+backup+'\nCOPY api.py '+destination+'\nCOPY dist/ /app/web/dist/\n')
docker('build','--network=none','--pull=false','-t','leroy-controller:nas-parity',str(folder))
after=json.loads(docker('image','inspect','leroy-controller:nas-parity'))[0]
assert before['Config']==after['Config'] and before['RootFS']['Layers']==after['RootFS']['Layers'][:-2]
subprocess.run(['docker','compose','up','-d','--no-deps','--wait','--wait-timeout','120','controller'],cwd=root,check=True,timeout=150)
current=json.loads(docker('inspect','leroy-nas-parity-controller-1'))[0]
assert current['Image']==after['Id']
actual=docker('exec','leroy-nas-parity-controller-1','python','-c','import hashlib,leroy.api;print(hashlib.sha256(open(leroy.api.__file__,"rb").read()).hexdigest())').strip()
assert actual==EXPECTED
print(json.dumps({'previous_image':before['Id'],'image':after['Id'],'api_sha256':actual,'dependencies_unchanged':True,'runtime_config_unchanged':True}))
"""
    result = run_script("python3 - <<'PY'\nEXPECTED=" + repr(digest) + "\n" + program + "\nPY\n",
                        CREDENTIALS, timeout=360)
    assert result.returncode == 0, result.stderr[-2000:]
    evidence = json.loads(result.stdout.splitlines()[-1])
    with closing(client()) as api:
        api.get("/health/ready").raise_for_status()
        assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
        for name, expected in assets.items():
            response = api.get("/" if name == "index.html" else "/" + name)
            response.raise_for_status()
            assert hashlib.sha256(response.content).hexdigest() == expected
    evidence.update(at=datetime.now(timezone.utc).isoformat(), readiness=True, graph_focus=True,
                    served_assets=assets)
    marker.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
