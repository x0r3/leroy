"""Repair the observed address collision only in the idle NAS acceptance stack.

Keep container IDs, images, data, resource limits and the closed CI journals.
Persist explicit addresses and verify starting the runner before PostgreSQL.
An interrupted mutation is inspected through its retained journal, never retried.
"""

import argparse
import json

import nas_release_vm as vm
from nas_followup_support import production_jobs
from nas_measurement_guard import assess
from nas_ssh import ROOT

PROGRAM = r'''
import hashlib,json,os,pathlib,subprocess,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert root.resolve()==root and (root/'.leroy-owned').is_file()
work=root/'control-network-recovery-20261026'
assert not work.exists(),'Inspect the retained recovery rather than replaying it'
network='leroy-nas-parity_default'
names=('postgres','controller','runner','docker')
def call(args,timeout=30):
 r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 assert r.returncode==0,'Owned network operation failed; inspect its retained journal'
 return r.stdout
def inspect(name):return json.loads(call(['docker','inspect',name]))[0]
def seven():
 for name in ('paperless','sonarr','radarr','sabnzbd','plex','yt-downloader-service','mail-ingest-service'):
  c=inspect(name);assert c['State']['Running'] and c['State'].get('Health',{}).get('Status')=='healthy'
def check_production():
 import xml.etree.ElementTree as ET
 home=pathlib.Path('/volume1/docker/jenkins/jobs')
 for name,row in EXPECTED.items():
  p=(home/name).resolve(strict=True);assert p.is_relative_to(home)
  number=int((p/'nextBuildNumber').read_text())-1 if (p/'nextBuildNumber').is_file() else 0
  assert number==row['number'],'New production work; stop only this recovery'
  if number:assert ET.parse(p/'builds'/str(number)/'build.xml').getroot().findtext('completed')=='true'
check_production();seven()
guard=json.loads((root/'resource-window-acceptance-20261017-y-rust-jenkins/state.json').read_text())
assert guard['phase']=='restored'
target=inspect('leroy-nas-release-target-vm')
assert target['Id']=='8d75ca62e00b3484b84ae54de5351245a70ad73a0885f85ed04577d653f83e74'
assert not target['State']['Running']
before={n:inspect('leroy-nas-parity-'+n+'-1') for n in names}
assert all(c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' for c in before.values())
assert before['runner']['NetworkSettings']['Networks'][network]['IPAddress']=='10.232.98.2'
assert before['docker']['NetworkSettings']['Networks'][network]['IPAddress']=='10.232.98.3'
assert not before['postgres']['State']['Running'] and 'Address already in use' in before['postgres']['State']['Error']
inner=['docker','exec',before['docker']['Id'],'docker']
assert call(inner+['inspect','jenkins-parity','--format','{{.State.Running}}']).strip()=='false'
assert not call(inner+['ps','-q','--filter','label=io.leroy.runner=runner-nas-parity']).strip()
net=json.loads(call(['docker','network','inspect',network]))[0]
assert net['Labels']['com.docker.compose.project']=='leroy-nas-parity'
assert all(c['Name'].startswith('leroy-nas-parity-') for c in net['Containers'].values())
assert all(c['IPv4Address']!='10.232.98.4/24' for c in net['Containers'].values())
override=root/'compose.override.yaml';raw=override.read_bytes();updated=json.loads(raw)
assert set(updated)=={'services'}
for name,address in [('postgres','10.232.98.2'),('docker','10.232.98.3'),('runner','10.232.98.4')]:
 service=updated['services'].setdefault(name,{})
 prior=service.get('networks')
 assert prior is None or prior=={'default':{'ipv4_address':address}}
 service['networks']={'default':{'ipv4_address':address}}
work.mkdir(mode=0o700)
def save(name,value):
 path=work/name
 with path.open('x') as stream:
  os.chmod(path,0o600);json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
save('containers-before.json',before)
save('network-before.json',net)
with (work/'compose.override.yaml.before').open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
(work/'compose.override.yaml.before').chmod(0o600)
save('started.json',{'at_epoch':time.time(),'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()})
call(['docker','stop','--time','20',before['runner']['Id'],before['controller']['Id']],timeout=65)
check_production()
def move(name,address):
 old=before[name];aliases=old['NetworkSettings']['Networks'][network].get('Aliases') or []
 call(['docker','network','disconnect','--force',net['Id'],old['Id']])
 args=['docker','network','connect','--ip',address]
 for alias in aliases:
  if alias:args+=['--alias',alias]
 call(args+[net['Id'],old['Id']])
 save(name+'-address-assigned.json',{'at_epoch':time.time(),'id':old['Id'],'address':address})
move('runner','10.232.98.4')
move('docker','10.232.98.3')
payload=(json.dumps(updated,indent=2)+'\n').encode()
temporary=root/'compose.override.network-recovery-20261026.tmp'
with temporary.open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
temporary.chmod(0o600);temporary.replace(override)
save('configuration-persisted.json',{'override_sha256':hashlib.sha256(payload).hexdigest()})
def start(name):
 check_production();call(['docker','start',before[name]['Id']])
 deadline=time.monotonic()+100
 while time.monotonic()<deadline:
  c=inspect(before[name]['Id'])
  if c['State']['Running'] and c['State'].get('Health',{}).get('Status','healthy')=='healthy':return c
  time.sleep(2)
 raise TimeoutError('Owned service did not become healthy: '+name)
start('postgres')
sql="select json_build_object('runs',(select count(*) from runs),'active',(select count(*) from runs where status in ('running','queued','waiting')),'steps',(select count(*) from steps),'artifacts',(select count(*) from artifacts),'fsync',current_setting('fsync'),'synchronous_commit',current_setting('synchronous_commit'),'full_page_writes',current_setting('full_page_writes'))"
def db():
 return json.loads(call(['docker','exec','-e','PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=10000',before['postgres']['Id'],'psql','-XqAt','-U','leroy','-d','leroy','-c',sql]))
database=db();assert database['active']==0
assert all(database[k]=='on' for k in ('fsync','synchronous_commit','full_page_writes'))
with (work/'database-before.dump').open('xb') as stream:
 r=subprocess.run(['docker','exec',before['postgres']['Id'],'pg_dump','-Fc','-U','leroy','-d','leroy'],stdout=stream,stderr=subprocess.PIPE,timeout=90)
 assert r.returncode==0;stream.flush();os.fsync(stream.fileno())
(work/'database-before.dump').chmod(0o600)
start('controller');start('runner')
save('first-recovery.json',{'at_epoch':time.time(),'database':db()})
# Repeat the formerly failing order, without running any CI job or rebooting the NAS.
call(['docker','stop','--time','20',before['runner']['Id'],before['controller']['Id'],before['postgres']['Id']],timeout=85)
start('runner')
runner_first=inspect(before['runner']['Id'])
assert runner_first['NetworkSettings']['Networks'][network]['IPAddress']=='10.232.98.4'
assert not inspect(before['postgres']['Id'])['State']['Running']
start('postgres');start('controller')
after={n:inspect(before[n]['Id']) for n in names}
for name,c in after.items():
 old=before[name]
 for key in ('Id','Image','Config','HostConfig'):assert c[key]==old[key],name+': '+key
 assert sorted(c['Mounts'],key=lambda m:m['Destination'])==sorted(old['Mounts'],key=lambda m:m['Destination'])
 assert c['State']['Running'] and not c['State']['OOMKilled']
 if name!='runner':assert c['State'].get('Health',{}).get('Status')=='healthy'
for name,address in [('postgres','10.232.98.2'),('docker','10.232.98.3'),('runner','10.232.98.4')]:
 c=after[name]['NetworkSettings']['Networks'][network]
 assert c['IPAddress']==address and c['IPAMConfig']['IPv4Address']==address
assert db()==database
seven();check_production()
result={'at_epoch':time.time(),'container_ids_images_config_resources_mounts_unchanged':True,
 'explicit_addresses':{'postgres':'10.232.98.2','docker':'10.232.98.3','runner':'10.232.98.4'},
 'runner_before_postgres_restart_passed':True,'database':database,
 'database_backup_sha256':hashlib.sha256((work/'database-before.dump').read_bytes()).hexdigest(),
 'seven_services_healthy':True,'ci_jobs_started':False,'production_modified':False,
 'graphato_sources_tests_or_limits_changed':False,'closed_window_reopened':False}
save('recovery-proof.json',result);print(json.dumps(result))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not args.apply:
        print('Use --apply for the observed, reviewed NAS-only network recovery.')
        return
    before = production_jobs()
    assert not before['active_builds'] and before['older_concurrent_build_history_verified']
    folder = ROOT / 'test-results/nas-parity/followup/control-network-recovery-20261026'
    assert not folder.exists()
    folder.mkdir()
    (folder / 'production-before.json').write_text(json.dumps(before, indent=2) + '\n')
    result = json.loads(vm.remote('EXPECTED=' + repr(before['jobs']) + '\n' + PROGRAM, sudo=True, timeout=600))
    after = production_jobs()
    result['production_observation'] = assess(before, after)
    (folder / 'recovery-proof.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
