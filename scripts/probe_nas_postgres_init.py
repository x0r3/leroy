"""Compare orphan reaping with/without Docker init on two disposable databases.

Uses the exact retained Graphato PostgreSQL image, sequentially in the owned
comparison daemon. No ports, persistent volumes, application sources or original
CI jobs are changed. This is a causal probe, not release acceptance.
"""

import json
from datetime import datetime, timezone

import nas_release_vm as vm
from nas_followup_support import production_jobs
from nas_measurement_guard import assess
from nas_ssh import ROOT

IMAGE = 'postgres@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2'
LABEL = 'io.leroy.postgres-init-probe=20261014'

PROGRAM = r'''
import json,pathlib,re,subprocess,time
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
outer=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-docker-1'],text=True,timeout=15))[0]
assert outer['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
prefix=['docker','exec',outer['Id'],'docker']
def docker(*args,timeout=25,check=True):
 r=subprocess.run(prefix+list(args),capture_output=True,text=True,timeout=timeout)
 if check and r.returncode:raise RuntimeError('Owned diagnostic Docker command failed: '+args[0])
 return r
docker('pull',IMAGE,timeout=180)
image=json.loads(docker('image','inspect',IMAGE).stdout)[0]
expected_config='sha256:b07129cc272f688c98f5b343138a0a52fa45b3d82f50d7a53ff441330624cd2e'
# Docker's classic and containerd stores expose different identity levels.
assert image['Id'] in {expected_config, IMAGE.split('@')[1],
 'sha256:63bdc97d67b5133bf0e5ebd500bec6d046fa851dc81340d838f0347e616107e8'}
assert image['Os']=='linux' and image['Architecture']=='amd64'
assert image['RootFS']['Layers']==EXPECTED_LAYERS
output={'image_identity':image['Id'],'same_original_postgres_rootfs':True,'cases':{},'original_ci_started':False,
 'original_application_sources_or_tests_changed':False,'acceptance_run':False}
for mode in ('without_init','with_init'):
 name='leroy-parity-pg-init-'+mode.replace('_','-')
 assert not docker('ps','-aq','--filter','name=^/'+name+'$').stdout.strip()
 identity=None
 try:
  args=['run','-d','--name',name,'--label',LABEL,'--network','none',
   '--memory','384m','--memory-swap','384m','--cpus','0.5','--pids-limit','64',
   '--read-only','--cap-drop','ALL','--cap-add','CHOWN','--cap-add','DAC_OVERRIDE','--cap-add','FOWNER',
   '--cap-add','SETGID','--cap-add','SETUID','--security-opt','no-new-privileges:true',
   '--tmpfs','/var/lib/postgresql:rw,nosuid,nodev,size=128m',
   '--tmpfs','/var/run/postgresql:rw,nosuid,nodev,size=2m',
   '--tmpfs','/tmp:rw,nosuid,nodev,size=8m',
   '--env','POSTGRES_USER=probe','--env','POSTGRES_DB=probe','--env','POSTGRES_HOST_AUTH_METHOD=trust']
  if mode=='with_init':args.append('--init')
  identity=docker(*args,image['Id'],'postgres','-c','shared_buffers=16MB','-c','max_connections=10').stdout.strip()
  assert re.fullmatch('[a-f0-9]{64}',identity)
  for _ in range(60):
   if docker('exec',identity,'pg_isready','-h','127.0.0.1','-U','probe','-d','probe',check=False).returncode==0:break
   time.sleep(1)
  else:raise RuntimeError('Disposable PostgreSQL did not become ready')
  version=docker('exec',identity,'postgres','--version').stdout.strip()
  docker('exec',identity,'psql','-h','127.0.0.1','-U','probe','-d','probe','-v','ON_ERROR_STOP=1','-c',
   'CREATE TABLE retained_marker(value integer); INSERT INTO retained_marker VALUES (42);')
  started=time.time()
  docker('exec',identity,'sh','-c','(sleep 2; exit 2) >/dev/null 2>&1 </dev/null &')
  time.sleep(5)
  for _ in range(15):
   sql=docker('exec',identity,'psql','-h','127.0.0.1','-U','probe','-d','probe','-Atc',
    'SELECT value FROM retained_marker;',check=False)
   if sql.returncode==0:break
   time.sleep(1)
  assert sql.returncode==0 and sql.stdout.strip()=='42'
  logs=docker('logs',identity).stdout+docker('logs',identity).stderr
  state=json.loads(docker('inspect',identity).stdout)[0]
  output['cases'][mode]={'version':version,'init':bool(state['HostConfig'].get('Init')),
   'postmaster_is_pid_one':mode=='without_init','exit_two_orphan_injected':True,
   'untracked_child_exit_two_count':len(re.findall(r'untracked child process \(PID [0-9]+\) exited with exit code 2',logs)),
   'database_reinitialization_count':logs.count('all server processes terminated; reinitializing'),
   'sql_marker_survives':sql.stdout.strip()=='42','running':state['State']['Running'],
   'oom_killed':state['State']['OOMKilled'],'elapsed_seconds':time.time()-started}
 finally:
  if identity:
   item=json.loads(docker('inspect',identity).stdout)[0]
   assert item['Name']=='/'+name and item['Config']['Labels'].get('io.leroy.postgres-init-probe')=='20261014'
   docker('rm','-f',identity)
   output['cases'].setdefault(mode,{})['owned_container_removed']=True
assert output['cases']['without_init']['untracked_child_exit_two_count']>=1
assert output['cases']['without_init']['database_reinitialization_count']>=1
assert output['cases']['with_init']['untracked_child_exit_two_count']==0
assert output['cases']['with_init']['database_reinitialization_count']==0
output.update(controlled_orphan_reproduction_passed=True,production_ready=False)
print(json.dumps(output))
'''


def main():
    folder = ROOT / 'test-results/nas-parity/followup/offline-forensics-20261014'
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / 'postgres-init-probe-started.json'
    assert not marker.exists(), 'Inspect the first diagnostic before another attempt'
    before = production_jobs()
    assert not before['active_builds'] and before['older_concurrent_build_history_verified']
    marker.write_text(json.dumps({'at': datetime.now(timezone.utc).isoformat(), 'production_before': before}) + '\n')
    retained = json.loads((folder / 'original-postgres-configuration.json').read_text())
    layers = retained['image_metadata']['rootfs']['diff_ids']
    program = 'IMAGE=' + repr(IMAGE) + '\nLABEL=' + repr(LABEL) + '\nEXPECTED_LAYERS=' + repr(layers) + '\n' + PROGRAM
    value = json.loads(vm.remote(program, timeout=360))
    value.update(at=datetime.now(timezone.utc).isoformat(), production_measurement=assess(before, production_jobs()))
    (folder / 'postgres-init-probe.json').write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value[key] for key in ('controlled_orphan_reproduction_passed', 'cases', 'production_ready')}))


if __name__ == '__main__':
    main()
