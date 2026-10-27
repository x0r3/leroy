"""Read the owned NAS control stack without exposing settings or credentials."""

import json
from datetime import datetime, timezone

import nas_release_vm as vm
from nas_followup_support import production_jobs
from nas_gitea_target import idle
from nas_ssh import ROOT

FOLDER = ROOT / "test-results/nas-parity/followup/control-latency-20261012"

PROGRAM = r'''
import json,pathlib,subprocess,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert root.resolve()==root and (root/'.leroy-owned').is_file()
def inspect(name):return json.loads(subprocess.check_output(['docker','inspect',name],text=True,timeout=15))[0]
def mount(path):
 r=subprocess.run(['findmnt','--json','-T',str(path),'-o','SOURCE,TARGET,FSTYPE'],capture_output=True,text=True,timeout=10)
 return json.loads(r.stdout)['filesystems'] if r.returncode==0 else []
def cgroup(pid):
 line=next(x for x in pathlib.Path('/proc',str(pid),'cgroup').read_text().splitlines() if x.startswith('0::'))
 p=pathlib.Path('/sys/fs/cgroup'+line[3:]);assert p.resolve().is_relative_to(pathlib.Path('/sys/fs/cgroup'))
 return {name:(p/name).read_text().strip() for name in ('memory.current','memory.swap.current','memory.low','memory.min','memory.max','memory.events','cpu.stat','io.pressure','memory.pressure') if (p/name).exists()}
services={}
for name in ('postgres','controller','runner','docker'):
 c=inspect('leroy-nas-parity-'+name+'-1')
 assert c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' and c['State']['Running']
 services[name]={'id':c['Id'],'image':c['Image'],'pid':c['State']['Pid'],
  'resources':{k:c['HostConfig'][k] for k in ('Memory','MemorySwap','MemoryReservation','NanoCpus','CpuShares')},
  'logging':c['HostConfig']['LogConfig'],'log_path':c['LogPath'],'log_mount':mount(c['LogPath']),
  'data_mounts':[{k:m[k] for k in ('Type','Source','Destination','RW')} for m in c['Mounts'] if m['Destination'] in ('/data','/var/lib/postgresql','/var/lib/docker')],
  'cgroup':cgroup(c['State']['Pid'])}
target=inspect('leroy-nas-release-target-vm')
assert not target['State']['Running']
probe=r"""
import httpx,json,time
from sqlalchemy import text
from leroy.config import Settings
from leroy.db import connect
engine,_=connect(Settings.load().database_url)
rows=[]
with httpx.Client(timeout=5) as api:
 for i in range(5):
  for path in ('/health/live','/health/ready'):
   at=time.perf_counter()
   try:r=api.get('http://127.0.0.1:8088'+path);status=r.status_code;error=None
   except Exception as e:status=None;error=type(e).__name__
   rows.append({'kind':path,'seconds':time.perf_counter()-at,'status':status,'error':error})
  at=time.perf_counter()
  try:
   with engine.connect() as db:
    db.execute(text('SET TRANSACTION READ ONLY'));db.execute(text("SET LOCAL statement_timeout='3s'"));assert db.scalar(text('SELECT 1'))==1
   error=None
  except Exception as e:error=type(e).__name__
  rows.append({'kind':'controller_to_postgres_select_1','seconds':time.perf_counter()-at,'error':error})
engine.dispose();print(json.dumps(rows))
"""
r=subprocess.run(['docker','exec','-i',services['controller']['id'],'python','-'],input=probe,capture_output=True,text=True,timeout=100)
assert r.returncode==0,'Control baseline probe failed; retain sanitized diagnostics'
print(json.dumps({'services':services,'latencies':json.loads(r.stdout),'test_vm_running':False,
 'host_memory_kib':{line.split(':')[0]:int(line.split()[1]) for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:','MemAvailable:','SwapTotal:','SwapFree:'))},
 'host_pressure':{name:pathlib.Path('/proc/pressure',name).read_text() for name in ('cpu','memory','io')},'production_modified':False}))
'''


def main():
    FOLDER.mkdir(parents=True, exist_ok=True)
    output = FOLDER / "initial-inspection.json"
    assert not output.exists(), "Retain the initial inspection rather than replacing it"
    idle()
    production = production_jobs()
    assert not production["active_builds"], "Wait for production before a latency probe"
    value = json.loads(vm.remote(PROGRAM, sudo=True, timeout=150))
    value.update(at=datetime.now(timezone.utc).isoformat(), production_before=production)
    output.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "services": {
                    name: {
                        "logging": row["logging"],
                        "log_mount": row["log_mount"],
                        "resources": row["resources"],
                    }
                    for name, row in value["services"].items()
                },
                "maximum_baseline_seconds": {
                    kind: max(row["seconds"] for row in value["latencies"] if row["kind"] == kind)
                    for kind in {row["kind"] for row in value["latencies"]}
                },
                "production_active": production["active_builds"],
            }
        )
    )


if __name__ == "__main__":
    main()
