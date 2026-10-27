"""Protect the measured owned controller working set without restarting services."""

import argparse
import json
from contextlib import closing

import nas_release_vm as vm
from compare_nas_antares import client
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT

FOLDER = ROOT / 'test-results/nas-parity/followup/control-working-set-20261015'
PROGRAM = r'''
import hashlib,json,os,pathlib,stat,subprocess,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert root.resolve()==root and (root/'.leroy-owned').is_file()
work=root/'control-working-set-20261015'
assert not work.exists(),'Inspect retained deployment instead of repeating it'
unit=pathlib.Path('/etc/systemd/system/leroyparity.slice')
override=root/'compose.override.yaml'
for path in (unit,override):
 s=path.stat();assert path.resolve(strict=True)==path and not path.is_symlink()
 assert s.st_uid==0 and s.st_nlink==1 and stat.S_ISREG(s.st_mode)
unit_before=unit.read_bytes()
assert unit_before.startswith(b'# Leroy owned isolated NAS test control services only\n')
assert unit_before.count(b'MemoryLow=320M\n')==1 and b'MemoryMin=0\n' in unit_before
unit_after=unit_before.replace(b'MemoryLow=320M\n',b'MemoryLow=448M\n')
parent=pathlib.Path('/sys/fs/cgroup/leroyparity.slice')
assert parent.resolve(strict=True)==parent
assert int((parent/'memory.low').read_text())==320*1024**2
assert (parent/'memory.min').read_text().strip()=='0'

def call(args,timeout=30):
 r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 assert r.returncode==0,'Owned working-set operation failed; output withheld'
 return r.stdout

def inspect(name):
 return json.loads(call(['docker','inspect','leroy-nas-parity-'+name+'-1']))[0]

names=('controller','postgres','runner','docker')
before={name:inspect(name) for name in names}
assert all(c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' and c['State']['Running'] for c in before.values())
assert before['controller']['HostConfig']['Memory']==before['controller']['HostConfig']['MemorySwap']==512*1024**2
reservations={'controller':128*1024**2,'postgres':128*1024**2,'runner':64*1024**2}
assert all(before[name]['HostConfig']['MemoryReservation']==value and before[name]['HostConfig']['CgroupParent']=='leroyparity.slice' for name,value in reservations.items())
target=json.loads(call(['docker','inspect','leroy-nas-release-target-vm']))[0]
assert not target['State']['Running']
inner=['docker','exec',before['docker']['Id'],'docker']
assert call(inner+['inspect','jenkins-parity','--format','{{.State.Running}}']).strip()=='false'
assert not call(inner+['ps','-q','--filter','label=io.leroy.runner=runner-nas-parity']).strip()
global_parent=pathlib.Path('/sys/fs/cgroup/system.slice')
global_before={key:(global_parent/key).read_text() for key in ('memory.low','memory.min','memory.high','memory.max')}
compose=['docker','compose','--project-directory',str(root)]
original=json.loads(call(compose+['config','--format','json']))
reservation=original['services']['controller']['mem_reservation']
assert type(reservation) in (int,str) and int(reservation)==128*1024**2
raw=override.read_bytes();candidate=json.loads(raw)
candidate['services']['controller']['mem_reservation']='256m'
expected=json.loads(json.dumps(original))
expected['services']['controller']['mem_reservation']=type(reservation)(256*1024**2)
work.mkdir(mode=0o700)

def persist(path,data,mode=0o600):
 with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 path.chmod(mode)

persist(work/'containers-before.json',json.dumps(before).encode())
persist(work/'compose.override.before',raw)
persist(work/'leroyparity.slice.before',unit_before)
staged=work/'compose.override.candidate.json'
persist(staged,(json.dumps(candidate,indent=2)+'\n').encode())
normalized=json.loads(call(compose+['-f',str(root/'compose.yaml'),'-f',str(staged),'config','--format','json']))
assert normalized==expected,'Changes beyond the one controller reservation'
with (work/'database-before.dump').open('xb') as f:
 result=subprocess.run(['docker','exec',before['postgres']['Id'],'pg_dump','-U','leroy','-d','leroy','-Fc'],stdout=f,stderr=subprocess.PIPE,timeout=120)
 assert result.returncode==0,'Database backup failed; output withheld'
 f.flush();os.fsync(f.fileno())
(work/'database-before.dump').chmod(0o600)
persist(work/'intent.json',json.dumps({'at_epoch':time.time(),'controller_reservation_before':128*1024**2,'controller_reservation_after':256*1024**2,'own_parent_before':320*1024**2,'own_parent_after':448*1024**2,'service_restarts_permitted':False,'other_resources_permitted':False}).encode())

def replace(path,data):
 previous=path.stat();temporary=path.with_name(path.name+'.working-set-20261015.partial')
 persist(temporary,data,stat.S_IMODE(previous.st_mode))
 os.chown(temporary,previous.st_uid,previous.st_gid)
 os.replace(temporary,path)
 fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)

replace(unit,unit_after)
replace(override,staged.read_bytes())
call(['systemctl','daemon-reload'])
call(['systemctl','set-property','--runtime','leroyparity.slice','MemoryLow=448M'])
call(['docker','update','--memory-reservation','256m',before['controller']['Id']])
after={name:inspect(name) for name in names}
for name,old in before.items():
 actual=after[name]
 for key in ('Id','Image','Config','NetworkSettings'):
  assert actual[key]==old[key],name+' '+key+' changed'
 assert sorted(actual['Mounts'],key=lambda mount:json.dumps(mount,sort_keys=True))==sorted(old['Mounts'],key=lambda mount:json.dumps(mount,sort_keys=True)),name+' mounts changed'
 assert actual['State']['Running'] and actual['State']['Pid']==old['State']['Pid'] and actual['RestartCount']==old['RestartCount']
 resources=json.loads(json.dumps(old['HostConfig']))
 if name=='controller':resources['MemoryReservation']=256*1024**2
 assert actual['HostConfig']==resources,'Unrelated runtime resource changed'
 relative=next(line[3:] for line in pathlib.Path('/proc',str(actual['State']['Pid']),'cgroup').read_text().splitlines() if line.startswith('0::'))
 if name in reservations:
  group=pathlib.Path('/sys/fs/cgroup')/relative.lstrip('/')
  assert group.resolve(strict=True)==group and group.parent==parent
  assert int((group/'memory.low').read_text())==(256*1024**2 if name=='controller' else reservations[name])
  assert (group/'memory.min').read_text().strip()=='0'
assert int((parent/'memory.low').read_text())==448*1024**2 and (parent/'memory.min').read_text().strip()=='0'
assert global_before=={key:(global_parent/key).read_text() for key in global_before}
assert unit.read_bytes()==unit_after and json.loads(call(compose+['config','--format','json']))==expected
sql="select json_build_object('fsync',current_setting('fsync'),'synchronous_commit',current_setting('synchronous_commit'),'full_page_writes',current_setting('full_page_writes'))"
durability=json.loads(call(['docker','exec',before['postgres']['Id'],'psql','-X','-qAt','-U','leroy','-d','leroy','-c',sql]))
assert all(value=='on' for value in durability.values())
proof={'at_epoch':time.time(),'controller_reservation_before_bytes':128*1024**2,'controller_reservation_after_bytes':256*1024**2,
 'own_parent_memory_low_before_bytes':320*1024**2,'own_parent_memory_low_after_bytes':448*1024**2,
 'controller_hard_limit_bytes':512*1024**2,'hard_protection_bytes':0,'best_effort_only':True,
 'images_service_ids_pids_mounts_and_other_resources_unchanged':True,'global_parent_settings_unchanged':True,
 'postgres_durability':durability,'database_backup_sha256':hashlib.file_digest((work/'database-before.dump').open('rb'),'sha256').hexdigest(),
 'unit_before_sha256':hashlib.sha256(unit_before).hexdigest(),'unit_after_sha256':hashlib.sha256(unit_after).hexdigest(),
 'override_before_sha256':hashlib.sha256(raw).hexdigest(),'override_after_sha256':hashlib.sha256(override.read_bytes()).hexdigest(),
 'ci_lease_deadlines_changed':False,'original_sources_tests_or_fixture_limits_changed':False,'production_modified':False,
 'services_paused':False,'workload_acceptance_proven':False}
persist(work/'deployment-proof.json',(json.dumps(proof,indent=2)+'\n').encode())
print(json.dumps(proof))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume-read-only-preflight', action='store_true')
    args = parser.parse_args()
    assert FOLDER.exists() == args.resume_read_only_preflight, 'Inspect the retained operation before repeating it'
    assert not (FOLDER / 'deployment-proof.json').exists(), 'Retain the completed deployment'
    if args.resume_read_only_preflight:
        preflight = json.loads((FOLDER / 'preflight-observation.json').read_text())
        assert preflight['deployment_directory_exists'] is False
    idle()
    assert not vm.state()['State']['Running']
    if not FOLDER.exists():
        FOLDER.mkdir()
    phase = 'working-set-reservation-resume' if args.resume_read_only_preflight else 'working-set-reservation'
    marker = begin(FOLDER, phase)
    try:
        proof = json.loads(vm.remote(PROGRAM, sudo=True, timeout=300))
        (FOLDER / 'deployment-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
        with closing(client()) as api:
            response = api.get('/health/ready')
            response.raise_for_status()
        print(json.dumps(proof), flush=True)
    finally:
        finish(FOLDER, phase, marker)


if __name__ == '__main__':
    main()
