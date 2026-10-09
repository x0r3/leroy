"""Collect bounded controller/runner/database evidence for the retained interrupted attempt."""

import json
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script
from stage_nas_production_graphato import COMMIT

PROGRAM = r'''
import json,pathlib,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
secrets=[(root/'config'/name).read_text().strip() for name in ['admin_password','db_password','runner_token','jenkins_password']]
def scrub(value):
 if isinstance(value,dict):return {k:scrub(v) for k,v in value.items()}
 if isinstance(value,list):return [scrub(v) for v in value]
 if isinstance(value,str):
  for secret in secrets:
   if secret:value=value.replace(secret,'[REDACTED]')
 return value
rows={}
for role in ['controller','runner','postgres']:
 name='leroy-nas-parity-'+role+'-1'
 info=json.loads(subprocess.check_output(['docker','inspect',name],text=True,timeout=20))[0]
 assert info['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
 group=pathlib.Path('/sys/fs/cgroup/system.slice','docker-'+info['Id']+'.scope')
 pressure={}
 for key in ['memory.current','memory.max','memory.swap.current','memory.events','io.pressure','memory.pressure','cpu.stat']:
  if (group/key).is_file():pressure[key]=(group/key).read_text()
 logs=subprocess.run(['docker','logs','--timestamps','--since','2026-10-05T21:53:00Z','--tail','500',name],text=True,capture_output=True,timeout=20)
 assert logs.returncode==0 and len(logs.stdout)+len(logs.stderr)<1024**2
 rows[role]={'id':info['Id'],'state':info['State']['Status'],'oom_killed':info['State']['OOMKilled'],'restart_count':info['RestartCount'],'limits':{k:info['HostConfig'][k] for k in ['Memory','MemorySwap','NanoCpus']},'pressure':pressure,'logs':logs.stdout+logs.stderr}
print(json.dumps(scrub({'read_only':True,'production_modified':False,'containers':rows})))
'''


def main():
    folder = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / COMMIT
    destination = folder / 'leroy-interruption-runtime.json'
    assert not destination.exists(), 'Retain the first post-interruption observation'
    response = run_script("python3 - <<'PY'\n" + PROGRAM + '\nPY\n', ROOT / '.local/nas-ssh.json', sudo=True, timeout=90)
    if response.returncode:
        raise RuntimeError(response.stderr[-1500:])
    record = json.loads(response.stdout)
    record['at'] = datetime.now(timezone.utc).isoformat()
    destination.write_text(json.dumps(record, indent=2) + '\n')
    for role, data in record['containers'].items():
        print(role, json.dumps({k: v for k, v in data.items() if k != 'logs'}))
        print(data['logs'][-4000:])


if __name__ == '__main__':
    main()
