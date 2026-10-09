"""Freeze owned stack image/config identities without exporting environment or secrets."""

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script

PROGRAM = r'''
import hashlib,json,pathlib,subprocess,tomllib
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
prefix=['docker','exec','leroy-nas-parity-docker-1','docker']
services={}
for service in ['controller','runner','postgres','docker','vm-access']:
 name='leroy-nas-parity-'+service+'-1'
 info=json.loads(subprocess.check_output(['docker','inspect',name],text=True,timeout=30))[0]
 assert info['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
 host=info['HostConfig']
 services[service]={'container_id':info['Id'],'image_id':info['Image'],'configured_image':info['Config']['Image'],
  'running':info['State']['Running'],'restart_count':info['RestartCount'],
  'health':info['State'].get('Health',{}).get('Status'),
  'memory_bytes':host['Memory'],'memory_and_swap_bytes':host['MemorySwap'],
  'memory_reservation_bytes':host['MemoryReservation'],'nano_cpus':host['NanoCpus']}
 assert services[service]['running']
profiles=tomllib.loads((root/'config/runner.toml').read_text())['profiles']
jobs={}
for name,spec in profiles.items():
 image=json.loads(subprocess.check_output(prefix+['image','inspect',spec['image']],text=True,timeout=30))[0]
 jobs[name]={'image_tag':spec['image'],'image_id':image['Id'],'rootfs_layers':image['RootFS']['Layers'],
  'memory':spec.get('memory'),'memory_swap':spec.get('memory_swap'),'cpus':spec.get('cpus')}
files={name:hashlib.sha256((root/name).read_bytes()).hexdigest()
       for name in ['compose.yaml','dind.sh','config/runner.toml','config/leroy.toml']}
if (root/'compose.release.json').is_file():
 files['compose.release.json']=hashlib.sha256((root/'compose.release.json').read_bytes()).hexdigest()
images=set(row['image_id'] for row in services.values())
controller=json.loads(subprocess.check_output(['docker','image','inspect',services['controller']['image_id']],text=True))[0]
runner=json.loads(subprocess.check_output(['docker','image','inspect',services['runner']['image_id']],text=True))[0]
assert controller['Id'] in images and runner['Id'] in images
print(json.dumps({'services':services,'job_profiles':jobs,'configuration_sha256':files,
 'read_only':True,'secret_values_exported':False,'production_modified':False}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--phase", choices=["before", "final"], required=True)
    args = parser.parse_args()
    assert re.fullmatch(r"[a-f0-9]{40}", args.commit)
    folder = ROOT / "test-results/nas-parity/followup/candidates/graphato" / args.commit
    assert (folder / "frozen-master.json").is_file()
    destination = folder / ("nas-release-configuration-" + args.phase + ".json")
    assert not destination.exists(), "Keep the first configuration observation"
    result = run_script("python3 - <<'PY'\n" + PROGRAM + "\nPY\n", ROOT / ".local/nas-ssh.json", timeout=90)
    assert result.returncode == 0, result.stderr[-1500:]
    record = json.loads(result.stdout)
    record.update(at=datetime.now(timezone.utc).isoformat(), comparison_commit=args.commit, phase=args.phase)
    destination.write_text(json.dumps(record, indent=2) + "\n")
    local = {name: hashlib.sha256((ROOT / "src/leroy" / name).read_bytes()).hexdigest()
             for name in ["worker.py", "runner.py", "actions.py", "api.py"]}
    (folder / ("local-release-code-" + args.phase + ".json")).write_text(json.dumps(local, indent=2) + "\n")
    print(json.dumps({"phase": args.phase, "services": {name: row['image_id'] for name, row in record['services'].items()},
                      "job_images": {name: row['image_id'] for name, row in record['job_profiles'].items()},
                      "secret_values_exported": False}), flush=True)


if __name__ == "__main__":
    main()
