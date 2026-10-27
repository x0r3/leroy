"""Give only the idle owned test engine recursive soft reclaim protection.

Recreate the outer daemon with exactly the same persistent engine, images,
inner container identities, and hard resources. Never change system.slice.
An uncertain deployment is retained for inspection, never blindly retried.
"""
import argparse
import json

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT

FOLDER = ROOT / 'test-results/nas-parity/followup/engine-memory-20261015'
PROGRAM = r'''
import copy,hashlib,json,os,pathlib,stat,subprocess,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert root.resolve()==root and (root/'.leroy-owned').is_file()
work=root/'engine-memory-20261015';assert not work.exists(),'Inspect retained attempt; do not repeat'
def call(args,timeout=30):
 r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 assert r.returncode==0,'Owned engine operation failed; output withheld'
 return r.stdout
def inspect(n):return json.loads(call(['docker','inspect',n]))[0]
def inner(outer,args):return call(['docker','exec',outer['Id'],'docker']+args)
def persist(p,data):
 with p.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 p.chmod(0o600)
def replace(p,data):
 previous=p.stat();candidate=p.with_name(p.name+'.engine-memory.partial')
 persist(candidate,data);os.chown(candidate,previous.st_uid,previous.st_gid);candidate.chmod(stat.S_IMODE(previous.st_mode));os.replace(candidate,p)
 fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def cg(pid):
 rel=next(l[3:] for l in pathlib.Path('/proc',str(pid),'cgroup').read_text().splitlines() if l.startswith('0::'))
 return pathlib.Path('/sys/fs/cgroup')/rel.lstrip('/')
def daemon_stop_marker(c):
 r=subprocess.run(['docker','logs','--tail','1000',c['Id']],capture_output=True,text=True,timeout=20)
 assert r.returncode==0
 lines=[l for l in (r.stdout+'\n'+r.stderr).splitlines() if 'Daemon shutdown complete' in l]
 return hashlib.sha256(lines[-1].encode()).hexdigest() if lines else None
before={n:inspect('leroy-nas-parity-'+n+'-1') for n in ('controller','postgres','runner','docker')}
assert all(c['State']['Running'] and c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' for c in before.values())
outer=before['docker'];assert outer['Id']=='d1b420ce3faddfcc63eb33e1a32e7fca911372bf658944cb8cf1b9051e350617'
assert outer['HostConfig']['CgroupParent']=='' and outer['HostConfig']['MemoryReservation']==0
assert outer['HostConfig']['Memory']==4608*1024**2 and outer['HostConfig']['MemorySwap']==7680*1024**2
assert 'memory_recursiveprot' in next(l for l in pathlib.Path('/proc/self/mountinfo').read_text().splitlines() if ' - cgroup2 ' in l)
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
assert not inner(outer,['ps','-q','--filter','label=io.leroy.runner=runner-nas-parity']).strip()
specs={n:json.loads(inner(outer,['inspect',n]))[0] for n in ('gitea','jenkins-parity')}
assert specs['gitea']['State']['Running'] and not specs['jenkins-parity']['State']['Running']
assert all(c['Config']['Labels'].get('io.leroy.nas-parity')=='true' for c in specs.values())
assert next(m['Source'] for m in outer['Mounts'] if m['Destination']=='/var/lib/docker')=='/overlay/leroy-nas-parity-engine-test/20261015-b/engine'
for n in ('paperless','sonarr','radarr','sabnzbd','plex','yt-downloader-service','mail-ingest-service'):
 c=inspect(n);assert c['State']['Running'] and c['State'].get('Health',{}).get('Status') in (None,'healthy')
global_group=pathlib.Path('/sys/fs/cgroup/system.slice')
global_before={k:(global_group/k).read_text() for k in ('memory.low','memory.min','memory.high','memory.max')}
override=root/'compose.override.yaml';raw=override.read_bytes();candidate=json.loads(raw)
assert not candidate['services']['docker'].get('cgroup_parent') and not candidate['services']['docker'].get('mem_reservation')
candidate['services']['docker'].update(cgroup_parent='-.slice',mem_reservation='1536m')
compose=['docker','compose','--project-directory',str(root)]
original=json.loads(call(compose+['config','--format','json']))
expected=copy.deepcopy(original);expected['services']['docker'].update(cgroup_parent='-.slice',mem_reservation='1610612736')
work.mkdir(mode=0o700)
persist(work/'containers-before.json',json.dumps(before).encode());persist(work/'inner-before.json',json.dumps(specs).encode());persist(work/'override-before.json',raw)
staged=work/'override-candidate.json';persist(staged,(json.dumps(candidate,indent=2)+'\n').encode())
normalized=json.loads(call(compose+['-f',str(root/'compose.yaml'),'-f',str(staged),'config','--format','json']))
actual_res=normalized['services']['docker']['mem_reservation'];expected['services']['docker']['mem_reservation']=type(actual_res)(1536*1024**2)
assert normalized==expected,'Compose differences beyond engine parent and soft protection'
persist(work/'intent.json',json.dumps({'at_epoch':time.time(),'engine_reservation_bytes':1536*1024**2,'parent':'-.slice','hard_limits_unchanged':True,'graphato_and_lease_changes':False}).encode())
prior=daemon_stop_marker(outer)
call(['docker','stop','--time','30',before['runner']['Id']],50)
try:
 call(['docker','stop','--time','90',outer['Id']],120)
 stopped=inspect(outer['Id']);completed=daemon_stop_marker(outer)
 assert not stopped['State']['Running'] and not stopped['State']['OOMKilled'] and completed and completed!=prior
 persist(work/'daemon-stopped.json',json.dumps({'daemon_shutdown_completed':True,'shutdown_marker_sha256':completed,'exit_code':stopped['State']['ExitCode']}).encode())
 replace(override,staged.read_bytes())
 call(compose+['up','-d','--no-deps','--no-build','--pull','never','docker'],120)
 until=time.monotonic()+120
 while time.monotonic()<until:
  current=inspect('leroy-nas-parity-docker-1')
  if current['State']['Running'] and current['State'].get('Health',{}).get('Status')=='healthy':break
  time.sleep(2)
 else:raise TimeoutError('Owned engine not healthy')
 def config(c):
  v=copy.deepcopy(c['Config']);assert v['Hostname']==c['Id'][:12];v['Hostname']='<generated>';v['Env']=sorted(v['Env'])
  for k in ('com.docker.compose.config-hash','com.docker.compose.depends_on'):v['Labels'].pop(k,None)
  return v
 assert current['Image']==outer['Image'] and config(current)==config(outer)
 assert sorted(current['Mounts'],key=lambda m:m['Destination'])==sorted(outer['Mounts'],key=lambda m:m['Destination'])
 h=copy.deepcopy(current['HostConfig']);h['CgroupParent']='';h['MemoryReservation']=0
 old=copy.deepcopy(outer['HostConfig'])
 for v in (h,old):
  if v.get('Binds'):v['Binds']=sorted(v['Binds'])
  if v.get('Mounts'):v['Mounts']=sorted(v['Mounts'],key=lambda m:m['Target'])
 assert h==old,'Unrelated engine resources changed'
 group=cg(current['State']['Pid']);scope=group.parent if group.name=='init' else group
 assert scope.parent==pathlib.Path('/sys/fs/cgroup') and scope.name=='docker-'+current['Id']+'.scope'
 assert (scope/'memory.low').read_text().strip()==str(1536*1024**2) and (scope/'memory.min').read_text().strip()=='0'
 assert inner(current,['ps','-q','--filter','label=io.leroy.runner=runner-nas-parity']).strip()==''
 after_inner={n:json.loads(inner(current,['inspect',n]))[0] for n in specs}
 for n,c in specs.items():
  a=after_inner[n]
  assert all(a[k]==c[k] for k in ('Id','Image','Config','HostConfig')),'Inner container configuration changed'
  assert sorted(a['Mounts'],key=lambda m:m['Destination'])==sorted(c['Mounts'],key=lambda m:m['Destination'])
 if not after_inner['gitea']['State']['Running']:inner(current,['start','gitea'])
 assert not after_inner['jenkins-parity']['State']['Running']
 assert all(inspect(before[n]['Id'])['State']['Pid']==before[n]['State']['Pid'] for n in ('controller','postgres'))
 assert global_before=={k:(global_group/k).read_text() for k in global_before}
 assert json.loads(call(compose+['config','--format','json']))==expected
 call(['docker','start',before['runner']['Id']],40)
 proof={'at_epoch':time.time(),'engine_container_id':current['Id'],'engine_image':current['Image'],'cgroup_path':str(scope),'engine_memory_low_bytes':1536*1024**2,
 'hard_limits_mounts_images_inner_ids_and_configs_unchanged':True,'controller_postgres_not_restarted':True,'global_parent_settings_unchanged':True,
 'recursive_protection_mount_verified':True,'best_effort_only':True,'production_modified':False,'graphato_sources_tests_and_limits_changed':False,
 'lease_and_http_timeouts_changed':False,'workload_validation_pending':True}
 persist(work/'deployment-proof.json',json.dumps(proof,indent=2).encode())
 print(json.dumps(proof))
except Exception as error:
 persist(work/'failure.json',json.dumps({'at_epoch':time.time(),'error_type':type(error).__name__,'blind_retry_forbidden':True}).encode())
 # Retain the engine and its unchanged data for inspection. Do not roll back an
 # uncertain healthy engine or start a runner before validation has completed.
 raise
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', required=True)
    parser.parse_args()
    assert not FOLDER.exists(), 'Inspect existing deployment instead of repeating it'
    idle()
    FOLDER.mkdir()
    marker = begin(FOLDER, 'engine-memory')
    (FOLDER / 'deployment-program.py').write_text(PROGRAM)
    proof = json.loads(vm.remote(PROGRAM, sudo=True, timeout=540))
    (FOLDER / 'deployment-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    finish(FOLDER, 'engine-memory', marker)
    print(json.dumps(proof), flush=True)


if __name__ == '__main__':
    main()
