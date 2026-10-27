"""Give only the idle NAS test control services an effective memory reservation.

The top-level slice avoids the zero reservation of system.slice. This is a
best-effort protection, not a hard allocation. Images, service limits, database
durability, worker settings, and application tests remain unchanged.
"""

import argparse
import json
from datetime import datetime, timezone

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT

FOLDER = ROOT / "test-results/nas-parity/followup/control-stability-20261012"
PROGRAM = r'''
import hashlib,json,os,pathlib,subprocess,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert root.resolve()==root and (root/'.leroy-owned').is_file()
work=root/'control-memory-group-20261012'
assert work.exists()==RESUME,'Retain uncertain deployment; only explicit inspected recovery'
unit=pathlib.Path('/etc/systemd/system/leroyparity.slice')
unit_text='# Leroy owned isolated NAS test control services only\n[Unit]\nDescription=Leroy isolated control services\n[Slice]\nMemoryAccounting=yes\nMemoryLow=320M\nMemoryMin=0\n'
assert unit.exists()==RESUME,'Do not replace an existing systemd unit'
def call(args,timeout=30):return subprocess.check_output(args,text=True,timeout=timeout)
def inspect(name):return json.loads(call(['docker','inspect',name]))[0]
before=json.loads((work/'containers-before.json').read_text()) if RESUME else {n:inspect('leroy-nas-parity-'+n+'-1') for n in ('controller','postgres','runner','docker')}
assert all(c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' and c['State']['Running'] for c in before.values())
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
inner=['docker','exec',before['docker']['Id'],'docker']
assert call(inner+['inspect','jenkins-parity','--format','{{.State.Running}}']).strip()=='false'
assert not call(inner+['ps','-q','--filter','label=io.leroy.runner=runner-nas-parity']).strip()
assert json.loads(call(['docker','info','--format','{{json .CgroupDriver}}']))=='systemd'
reservations={'controller':128*1024**2,'postgres':128*1024**2,'runner':64*1024**2}
assert all(before[n]['HostConfig']['MemoryReservation']==v and not before[n]['HostConfig']['CgroupParent'] for n,v in reservations.items())
if not RESUME:work.mkdir(mode=0o700)
def persist(path,data):
 with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 path.chmod(0o600)
override=root/'compose.override.yaml';raw=(work/'compose.override.yaml.before').read_bytes() if RESUME else override.read_bytes();updated=json.loads(raw)
assert set(updated)=={'services'}
for n in reservations:updated['services'].setdefault(n,{})['cgroup_parent']='leroyparity.slice'
if not RESUME:
 persist(work/'compose.override.yaml.before',raw)
 persist(work/'containers-before.json',json.dumps(before).encode())
 with (work/'database-before.dump').open('xb') as f:
  subprocess.run(['docker','exec',before['postgres']['Id'],'pg_dump','-U','leroy','-d','leroy','-Fc'],stdout=f,check=True,timeout=120)
  f.flush();os.fsync(f.fileno())
 (work/'database-before.dump').chmod(0o600)
compose=['docker','compose','--project-directory',str(root)]
configuration=json.loads(call(compose+(['-f',str(root/'compose.yaml'),'-f',str(work/'compose.override.yaml.before')] if RESUME else [])+['config','--format','json']))
if RESUME:
 assert override.read_text()==json.dumps(updated,indent=2)+'\n'
 assert unit.read_text()==unit_text
else:override.write_text(json.dumps(updated,indent=2)+'\n');override.chmod(0o600)
normalized=json.loads(call(compose+['config','--format','json']))
for n in reservations:assert normalized['services'][n].pop('cgroup_parent')=='leroyparity.slice'
assert normalized==configuration,'Only the owned cgroup parent may change'
if not RESUME:unit.write_text(unit_text)
unit.chmod(0o644)
subprocess.run(['systemctl','daemon-reload'],check=True,timeout=30)
subprocess.run(['systemctl','start','leroyparity.slice'],check=True,timeout=30)
parent=pathlib.Path('/sys/fs/cgroup/leroyparity.slice')
assert int((parent/'memory.low').read_text())==sum(reservations.values())
assert (parent/'memory.min').read_text().strip()=='0'
if not RESUME:subprocess.run(compose+['stop','--timeout','60','runner','controller','postgres'],check=True,timeout=200,stdout=subprocess.DEVNULL)
after={}
for n in ('postgres','controller','runner'):
 subprocess.run(compose+['up','-d','--no-deps','--pull','never',n],check=True,timeout=120,stdout=subprocess.DEVNULL)
 deadline=time.monotonic()+120
 while time.monotonic()<deadline:
  c=inspect('leroy-nas-parity-'+n+'-1')
  if c['State']['Running'] and c['State'].get('Health',{}).get('Status','healthy')=='healthy':break
  time.sleep(2)
 else:raise TimeoutError('Owned service failed health check: '+n)
 old=before[n]
 assert c['Image']==old['Image']
 assert sorted(c['Mounts'],key=lambda m:m['Destination'])==sorted(old['Mounts'],key=lambda m:m['Destination']),'Mounts'
 def normalized_config(info):
  value=json.loads(json.dumps(info['Config']))
  assert value['Hostname']==info['Id'][:12]
  value['Hostname']='<docker-generated>'
  value['Env']=sorted(value['Env'])
  value['Labels'].pop('com.docker.compose.config-hash',None)
  value['Labels'].pop('com.docker.compose.depends_on',None)
  return value
 assert normalized_config(c)==normalized_config(old),'Only Compose configuration hash may change'
 h=json.loads(json.dumps(c['HostConfig']));h['CgroupParent']=old['HostConfig']['CgroupParent']
 previous_h=json.loads(json.dumps(old['HostConfig']))
 for v in (h,previous_h):
  if v.get('Binds'):v['Binds']=sorted(v['Binds'])
 assert h==previous_h,'Service resources or runtime changed beyond parent'
 p=next(l[3:] for l in pathlib.Path('/proc',str(c['State']['Pid']),'cgroup').read_text().splitlines() if l.startswith('0::'))
 group=pathlib.Path('/sys/fs/cgroup'+p)
 assert group.parent==parent
 assert int((group/'memory.low').read_text())==reservations[n]
 assert (group/'memory.min').read_text().strip()=='0'
 after[n]={'image':c['Image'],'id':c['Id'],'cgroup_path':p,'memory_low_bytes':reservations[n],
  'memory_current_bytes':int((group/'memory.current').read_text()),'events':(group/'memory.events').read_text()}
dind=inspect(before['docker']['Id'])
for key in ('Id','Image','Config','HostConfig','Mounts','NetworkSettings'):assert dind[key]==before['docker'][key],'Owned Docker daemon must remain untouched'
assert dind['State']['Running']
sql="select json_build_object('fsync',current_setting('fsync'),'synchronous_commit',current_setting('synchronous_commit'),'full_page_writes',current_setting('full_page_writes'))"
durability=json.loads(call(['docker','exec','leroy-nas-parity-postgres-1','psql','-X','-qAt','-U','leroy','-d','leroy','-c',sql]))
assert all(v=='on' for v in durability.values())
result={'services':after,'parent_memory_low_bytes':sum(reservations.values()),'hard_memory_protection_bytes':0,
 'best_effort_only':True,'images_config_mounts_resources_unchanged':True,'docker_daemon_unchanged':True,
 'database_backup_sha256':hashlib.file_digest((work/'database-before.dump').open('rb'),'sha256').hexdigest(),
 'postgres_durability':durability,'lease_seconds_unchanged':90,'worker_confirmation_seconds_unchanged':45,
 'production_modified':False,'application_sources_or_tests_changed':False,'workload_validation_pending':True}
persist(work/'deployment-proof.json',json.dumps(result,indent=2).encode())
print(json.dumps(result))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume-inspected-config-hash-check', action='store_true')
    args = parser.parse_args()
    if not args.resume_inspected_config_hash_check:
        idle()
    output = FOLDER / "deployment-proof.json"
    assert not output.exists(), "Inspect the retained deployment before retrying"
    phase = ('memory-group-recovery-'+datetime.now(timezone.utc).strftime('%H%M%S')) if args.resume_inspected_config_hash_check else 'memory-group'
    marker = begin(FOLDER, phase)
    (FOLDER / (phase+'-started.json')).write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "production_before": marker}))
    try:
        result = json.loads(vm.remote('RESUME='+repr(args.resume_inspected_config_hash_check)+'\n'+PROGRAM, sudo=True, timeout=660))
        result["at"] = datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
    finally:
        finish(FOLDER, phase, marker)


if __name__ == "__main__":
    main()
