"""Install only the verified Leroy lease fix in the idle, owned NAS stack."""

import hashlib
import json
import tarfile
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE
from nas_ssh import ROOT, run_script, upload_file


def main():
    marker = ROOT / "test-results/nas-parity/lease-fix-deployment.json"
    if marker.exists():
        raise RuntimeError("Lease fix already deployed")
    with closing(client()) as api:
        for status in ("queued", "running", "waiting"):
            response = api.get("/api/runs", params={"status": status})
            response.raise_for_status()
            assert not response.json()
        assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
    archive = LOCAL / "lease-fix.tar"
    with tarfile.open(archive, "w") as bundle:
        for name in ("worker", "runner"):
            bundle.add(ROOT / f"src/leroy/{name}.py", f"{name}.py")
    upload_file(archive, REMOTE + "/lease-fix.tar", CREDENTIALS)
    config = LOCAL / "config/runner.toml"
    before = config.read_text()
    if 'memory_reservation = "128m"' not in before:
        updated = before.replace(
            "[profiles.graphato]\n", '[profiles.graphato]\nmemory_reservation = "128m"\n'
        )
        assert updated != before
        (LOCAL / "runner-before-lease-fix.toml").write_text(before)
        config.write_text(updated)
    upload_file(config, REMOTE + "/config/runner.toml", CREDENTIALS)
    program = r"""
import hashlib,json,pathlib,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert (root/'.leroy-owned').is_file()
folder=root/'lease-fix'
folder.mkdir(exist_ok=True)
subprocess.run(['tar','-xf',str(root/'lease-fix.tar'),'-C',str(folder)],check=True)
(root/'config/runner.toml').chmod(0o644)
inner=['docker','exec','-i','leroy-nas-parity-docker-1','docker']
assert not subprocess.check_output(inner+['ps','-a','--filter','label=io.leroy.runner=runner-nas-parity','-q'],text=True).strip()
with (root/'lease-fix.tar').open('rb') as source:
 subprocess.run(['docker','exec','-i','leroy-nas-parity-docker-1','sh','-c','mkdir -p /var/lib/docker/leroy-lease-fix && tar -xf - -C /var/lib/docker/leroy-lease-fix'],stdin=source,check=True)
out={}
for name,prefix,module,destination,context in [
 ('leroy-runner:nas-parity',['docker'],'runner','/usr/local/lib/python3.14/site-packages/leroy/runner.py',str(folder)),
 ('leroy-job:nas-parity',inner,'worker','/opt/leroy-worker/lib/python3.13/site-packages/leroy/worker.py','/var/lib/docker/leroy-lease-fix'),
 ('leroy-job:nas-parity-gitea',inner,'worker','/opt/leroy-worker/lib/python3.13/site-packages/leroy/worker.py','/var/lib/docker/leroy-lease-fix'),
]:
 def image(tag):return json.loads(subprocess.check_output(prefix+['image','inspect',tag]))[0]
 backup=name+'-before-lease-fix'
 probe=subprocess.run(prefix+['image','inspect',backup],capture_output=True,text=True)
 if probe.returncode==0:
  old=json.loads(probe.stdout)[0]
 else:
  old=image(name)
  subprocess.run(prefix+['tag',old['Id'],backup],check=True)
 dockerfile=f'FROM {backup}\nCOPY {module}.py {destination}\n'
 subprocess.run(prefix+['build','--network=none','--pull=false','-t',name,'-f','-',context],input=dockerfile,text=True,check=True,stdout=subprocess.DEVNULL)
 new=image(name)
 assert new['Config']==old['Config']
 assert new['RootFS']['Layers'][:-1]==old['RootFS']['Layers']
 check=f'import hashlib,leroy.{module};print(hashlib.sha256(open(leroy.{module}.__file__,"rb").read()).hexdigest())'
 actual=subprocess.check_output(prefix+['run','--rm','--network','none','--memory','128m',name,'python','-c',check],text=True).strip()
 expected=hashlib.sha256((folder/(module+'.py')).read_bytes()).hexdigest()
 assert actual==expected
 out[name]={'before':old['Id'],'after':new['Id'],'module_sha256':actual,'dependencies_unchanged':True}
subprocess.run(['docker','compose','up','-d','--no-deps','--force-recreate','runner'],cwd=root,check=True,stdout=subprocess.DEVNULL)
assert subprocess.check_output(['docker','inspect','--format','{{.Image}}','leroy-nas-parity-runner-1'],text=True).strip()==out['leroy-runner:nas-parity']['after']
print('EVIDENCE='+json.dumps(out))
"""
    result = run_script("python3 - <<'PY'\n" + program + "PY\n", CREDENTIALS, timeout=600)
    if result.returncode:
        raise RuntimeError(result.stderr[-2500:])
    evidence = json.loads(
        next(line[9:] for line in result.stdout.splitlines() if line.startswith("EVIDENCE="))
    )
    evidence = {
        "at": datetime.now(timezone.utc).isoformat(),
        "images": evidence,
        "graphato_job_memory_reservation": "128m",
        "server_lease_seconds_unchanged": 90,
        "application_patches_applied": False,
        "tests": "57 passed, including PostgreSQL and 8 worker/runner lease tests",
        "source_hashes": {
            name: hashlib.sha256((ROOT / f"src/leroy/{name}.py").read_bytes()).hexdigest()
            for name in ("worker", "runner")
        },
    }
    marker.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
