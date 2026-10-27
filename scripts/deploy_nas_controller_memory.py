"""Persist qualified memory headroom on the idle owned API, without recreation."""

import argparse
import json
from datetime import datetime, timezone

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from probe_nas_controller_memory import FOLDER

PROGRAM = r'''
import hashlib,json,os,pathlib,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert root.resolve()==root and (root/'.leroy-owned').is_file()
work=root/'controller-memory-deployment-20261013';assert work.exists()==RESUME
if not RESUME:work.mkdir(mode=0o700)
def call(args,timeout=30):
 r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 if r.returncode:raise RuntimeError('Scoped controller memory deployment failed; output withheld')
 return r.stdout.strip()
def inspect(n):return json.loads(call(['docker','inspect','leroy-nas-parity-'+n+'-1']))[0]
before=json.loads((work/'containers-before.json').read_text()) if RESUME else {n:inspect(n) for n in ('controller','postgres','runner','docker')}
if RESUME:assert all(inspect(n)['Id']==c['Id'] and inspect(n)['HostConfig']['Memory']==c['HostConfig']['Memory'] for n,c in before.items())
assert all(c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' and c['State']['Running'] for c in before.values())
assert before['controller']['HostConfig']['Memory']==before['controller']['HostConfig']['MemorySwap']==268435456
assert before['controller']['HostConfig']['CgroupParent']=='leroyparity.slice'
def persist(p,data):
 with p.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 p.chmod(0o600)
override=root/'compose.override.yaml';raw=(work/'compose.override.yaml.before').read_bytes() if RESUME else override.read_bytes()
if RESUME:assert override.read_bytes()==raw,'Resume only unchanged inspected staging'
else:
 persist(work/'compose.override.yaml.before',raw)
 persist(work/'containers-before.json',json.dumps(before).encode())
 with (work/'database-before.dump').open('xb') as f:
  r=subprocess.run(['docker','exec',before['postgres']['Id'],'pg_dump','-U','leroy','-d','leroy','-Fc'],stdout=f,stderr=subprocess.PIPE,timeout=120)
  assert r.returncode==0,'Database backup failed; output withheld'
  f.flush();os.fsync(f.fileno())
 (work/'database-before.dump').chmod(0o600)
compose=['docker','compose','--project-directory',str(root)]
original=json.loads(call(compose+['config','--format','json']))
value=json.loads(raw);value['services']['controller']['mem_limit']='512m';value['services']['controller']['memswap_limit']='512m'
candidate=work/'compose.override.candidate.json'
if RESUME:assert candidate.read_text()==json.dumps(value,indent=2)+'\n'
else:persist(candidate,(json.dumps(value,indent=2)+'\n').encode())
normalized=json.loads(call(compose+['-f',str(root/'compose.yaml'),'-f',str(candidate),'config','--format','json']))
expected=json.loads(json.dumps(original))
for key in ('mem_limit','memswap_limit'):
 assert type(expected['services']['controller'][key]) in (str,int)
 expected['services']['controller'][key]=type(expected['services']['controller'][key])(536870912)
assert normalized==expected,'Changes outside the two controller memory limits'
temporary=root/'compose.override.memory-20261013.partial'
persist(temporary,candidate.read_bytes());os.chown(temporary,override.stat().st_uid,override.stat().st_gid);os.chmod(temporary,override.stat().st_mode&0o777)
os.replace(temporary,override)
fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
try:os.fsync(fd)
finally:os.close(fd)
call(['docker','update','--memory','512m','--memory-swap','512m',before['controller']['Id']])
after={n:inspect(n) for n in before}
for n,previous in before.items():
 c=after[n]
 assert c['Id']==previous['Id'] and c['Image']==previous['Image'] and c['Config']==previous['Config']
 assert sorted(c['Mounts'],key=lambda m:json.dumps(m,sort_keys=True))==sorted(previous['Mounts'],key=lambda m:json.dumps(m,sort_keys=True))
 assert c['State']['Running'] and c['State']['Pid']==previous['State']['Pid'] and c['RestartCount']==previous['RestartCount']
 host=json.loads(json.dumps(c['HostConfig']));old=json.loads(json.dumps(previous['HostConfig']))
 if n=='controller':old['Memory']=old['MemorySwap']=536870912
 assert host==old,'Runtime configuration changed beyond API memory limits'
assert json.loads(call(compose+['config','--format','json']))==expected
proof={'controller_id':after['controller']['Id'],'controller_image':after['controller']['Image'],
 'old_memory_limit_bytes':268435456,'new_memory_limit_bytes':536870912,'swap_disabled':True,
 'controller_recreated_or_restarted':False,'controller_pid':after['controller']['State']['Pid'],
 'memory_reservation_and_parent_unchanged':True,'other_runtime_fields_images_mounts_and_service_ids_unchanged':True,
 'compose_change_persisted':True,'sources_tests_and_lease_deadlines_changed':False,'productive_services_modified':False,
 'database_backup_sha256':hashlib.file_digest((work/'database-before.dump').open('rb'),'sha256').hexdigest(),
 'before_override_sha256':hashlib.sha256(raw).hexdigest(),'after_override_sha256':hashlib.sha256(override.read_bytes()).hexdigest()}
persist(work/'deployment-proof.json',(json.dumps(proof,indent=2)+'\n').encode())
print(json.dumps(proof))
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume-validated-staging',action='store_true')
    args=parser.parse_args()
    qualified=json.loads((FOLDER/'ip-fixed/result.json').read_text())
    assert qualified['memory_limit_bytes']==512*1024**2 and qualified['oom_kills']==0
    idle()
    assert not vm.state()['State']['Running']
    phase='controller-memory-deployment-resume' if args.resume_validated_staging else 'controller-memory-deployment'
    before=begin(FOLDER,phase)
    try:
        value=json.loads(vm.remote('RESUME='+repr(args.resume_validated_staging)+'\n'+PROGRAM,sudo=True,timeout=240))
        value['at']=datetime.now(timezone.utc).isoformat()
        (FOLDER/'deployment-proof.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(value))
    finally:
        finish(FOLDER,phase,before)


if __name__=='__main__':
    main()
