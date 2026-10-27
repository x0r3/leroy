"""Suspend the owned NAS acceptance stack and prove native Jenkins is unchanged.

Keep databases, artifacts, disks and configurations for a later build server.
Do not stop, recreate, update, or write to native Jenkins or the seven NAS apps.
"""

import argparse
import json

import nas_release_vm as vm
from nas_followup_support import production_jobs
from nas_measurement_guard import assess
from nas_ssh import ROOT

PROGRAM = r'''
import hashlib,json,os,pathlib,subprocess,time
owner=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert owner.resolve()==owner and (owner/'.leroy-owned').is_file()
work=owner/'postponed-20261026';assert not work.exists(),'Inspect an existing suspension instead of repeating it'
def call(args,timeout=30):
 r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 assert r.returncode==0,'Owned suspension operation failed; inspect retained evidence'
 return r.stdout
def inspect(name):return json.loads(call(['docker','inspect',name]))[0]
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def fingerprint(c):
 v={key:c[key] for key in ('Id','Name','Image','Config','HostConfig')}
 v['Mounts']=sorted(c['Mounts'],key=lambda m:m['Destination'])
 return digest(v)
def summary(c):
 return {'id':c['Id'],'image':c['Image'],'name':c['Name'],'running':c['State']['Running'],
  'health':c['State'].get('Health',{}).get('Status'),'restart_policy':c['HostConfig']['RestartPolicy'],
  'configuration_sha256':fingerprint(c)}
def native_view(c):
 return {'name':c['Name'].lstrip('/'),'image_id':c['Image'],'image_tag':c['Config']['Image'],'user':c['Config']['User'],
  'running':c['State']['Running'],'memory':c['HostConfig']['Memory'],'memory_swap':c['HostConfig']['MemorySwap'],
  'nano_cpus':c['HostConfig']['NanoCpus'],'cpu_quota':c['HostConfig']['CpuQuota'],'cpu_period':c['HostConfig']['CpuPeriod'],
  'mounts':sorted([{k:m[k] for k in ('Type','Source','Destination','RW')} for m in c['Mounts']],key=lambda m:m['Destination']),
  'networks':sorted(c['NetworkSettings']['Networks']),'ports':c['NetworkSettings']['Ports']}
native=inspect('jenkins');assert native['State']['Running'] and native['State'].get('Health',{}).get('Status')=='healthy'
original=dict(BASELINE);original['mounts']=sorted(original['mounts'],key=lambda m:m['Destination']);original['networks']=sorted(original['networks'])
assert native_view(native)==original,'Do not roll back changed production settings or newer user data implicitly'
seven_names=('paperless','sonarr','radarr','sabnzbd','plex','yt-downloader-service','mail-ingest-service')
apps={n:inspect(n) for n in seven_names}
assert all(c['State']['Running'] and c['State'].get('Health',{}).get('Status')=='healthy' for c in apps.values())
names=('runner','controller','postgres','docker','vm-access')
before={n:inspect('leroy-nas-parity-'+n+'-1') for n in names}
assert all(c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' for c in before.values())
target=inspect('leroy-nas-release-target-vm')
assert target['Config']['Labels']['io.leroy.nas-release-target']=='0ad540dd578033d45e4d0c25d89fbe57b32102a4'
assert not target['State']['Running']
inner=['docker','exec',before['docker']['Id'],'docker']
assert not call(inner+['ps','-q','--filter','label=io.leroy.runner=runner-nas-parity']).strip()
private=json.loads(call(inner+['inspect','jenkins-parity']))[0]
assert private['Config']['Labels'].get('io.leroy.nas-parity')=='true' and not private['State']['Running']
work.mkdir(mode=0o700)
def save(name,value):
 p=work/name
 with p.open('x') as f:os.chmod(p,0o600);json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
save('started.json',{'at_epoch':time.time(),'reason':'Jenkins replacement postponed until a separate build server is available'})
save('before.json',{'native':summary(native),'apps':{n:summary(c) for n,c in apps.items()},'owned':{n:summary(c) for n,c in before.items()}})
call(['docker','stop','--time','30',before['runner']['Id']],timeout=45)
sql="select json_build_object('runs',(select count(*) from runs),'active',(select count(*) from runs where status in ('queued','running','waiting')),'steps',(select count(*) from steps),'artifacts',(select count(*) from artifacts))"
database=json.loads(call(['docker','exec','-e','PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=10000',before['postgres']['Id'],'psql','-XqAt','-U','leroy','-d','leroy','-c',sql]))
assert database['active']==0
call(['docker','stop','--time','30',before['controller']['Id']],timeout=45)
dump=work/'leroy.dump'
with dump.open('xb') as f:
 r=subprocess.run(['docker','exec',before['postgres']['Id'],'pg_dump','-Fc','-U','leroy','-d','leroy'],stdout=f,stderr=subprocess.PIPE,timeout=90)
 assert r.returncode==0;f.flush();os.fsync(f.fileno())
dump.chmod(0o600)
save('database-backup.json',{'sha256':hashlib.sha256(dump.read_bytes()).hexdigest(),'bytes':dump.stat().st_size,'rows':database})
for n in ('postgres','docker','vm-access'):
 call(['docker','stop','--time','60',before[n]['Id']],timeout=80)
for c in [*before.values(),target]:call(['docker','update','--restart=no',c['Id']])
unit='leroy-y2-disk-archive-20261026'
r=call(['systemctl','show',unit,'--property=InvocationID','--property=SubState'])
if 'InvocationID=2e0b8b9d8cdb497bbd9096bb7bf84ba1' in r:
 assert 'SubState=exited' in r;call(['systemctl','stop',unit])
group=pathlib.Path('/sys/fs/cgroup/leroyparity.slice')
if group.is_dir() and not any(p.read_text().strip() for p in group.rglob('cgroup.procs')):
 call(['systemctl','stop','leroyparity.slice'])
after={n:inspect(c['Id']) for n,c in before.items()}
assert all(not c['State']['Running'] and c['HostConfig']['RestartPolicy']['Name']=='no' for c in after.values())
current=inspect('jenkins');assert current['Id']==native['Id'] and fingerprint(current)==fingerprint(native)
assert native_view(current)==original and current['State'].get('Health',{}).get('Status')=='healthy'
for n,old in apps.items():
 c=inspect(old['Id']);assert fingerprint(c)==fingerprint(old)
 assert c['State']['Running'] and c['State'].get('Health',{}).get('Status')=='healthy'
ids=call(['docker','ps','-q','--filter','name=leroy']).split();assert not ids
result={'at_epoch':time.time(),'production_jenkins_healthy':True,'production_jenkins_matches_original_inventory':True,
 'production_jenkins_unchanged_during_suspension':True,'production_jenkins':native_view(current),
 'seven_original_services_healthy_and_unchanged':True,'seven_services':list(seven_names),
 'owned_test_containers_stopped':{n:summary(c) for n,c in after.items()},
 'test_vm_stopped':True,'test_container_automatic_restart_disabled':True,
 'test_volumes_disks_and_artifacts_retained':True,'database':database,'database_backup_sha256':hashlib.sha256(dump.read_bytes()).hexdigest(),
 'original_ci_dispatched':False,'native_jenkins_restarted_or_modified':False,'production_cutover':False}
save('suspension-proof.json',result);print(json.dumps(result))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    if not parser.parse_args().apply:
        print('Use --apply to suspend the reviewed, owned NAS acceptance stack.')
        return
    inventory = json.loads((ROOT / 'test-results/nas-parity/nas-inventory.json').read_text())
    baseline, = (row for row in inventory['containers'] if row['name'] == 'jenkins')
    before = production_jobs()
    assert not before['active_builds'] and before['older_concurrent_build_history_verified']
    folder = ROOT / 'test-results/nas-parity/followup/jenkins-only-20261026'
    assert not (folder / 'suspension-dispatched.json').exists()
    folder.mkdir(exist_ok=True)
    (folder / 'suspension-dispatched.json').write_text(json.dumps({'production_before': before}, indent=2) + '\n')
    value = json.loads(vm.remote('BASELINE=' + repr(baseline) + '\n' + PROGRAM, sudo=True, timeout=600))
    value['production_observation'] = assess(before, production_jobs())
    (folder / 'suspension-proof.json').write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps(value))


if __name__ == '__main__':
    main()
