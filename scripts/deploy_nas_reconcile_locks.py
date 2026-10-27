"""Install a PostgreSQL-qualified reconciliation fix in the idle NAS test API."""

import argparse
import json
import tarfile

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, upload_file

PROGRAM = r'''
import hashlib,json,os,pathlib,re,subprocess,tarfile,time,urllib.request
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
work=root/'reconcile-locks-deployment-20261014';assert work.exists()==RESUME
if not RESUME:work.mkdir(mode=0o700)
def call(args,timeout=30,**kw):
 r=subprocess.run(args,capture_output=True,timeout=timeout,**kw)
 assert r.returncode==0,'Scoped controller deployment failed; output withheld'
 return r.stdout
def inspect(name):return json.loads(call(['docker','inspect',name]))[0]
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
outer=inspect('leroy-nas-parity-docker-1');inner=['docker','exec',outer['Id'],'docker']
assert call(inner+['inspect','jenkins-parity','--format','{{.State.Running}}']).strip()==b'false'
assert not call(inner+['ps','-aq','--filter','label=io.leroy.runner=runner-nas-parity']).strip()
before=(json.loads((work/'containers-before.json').read_text()) if RESUME else
 {s:inspect('leroy-nas-parity-'+s+'-1') for s in ('controller','postgres','runner','docker')})
if RESUME:
 for service,prior in before.items():
  current=inspect('leroy-nas-parity-'+service+'-1')
  if service=='controller' and VERIFY_APPLIED:
   assert current['Image']==QUALIFIED_IMAGE and current['State']['Running']
  else:
   assert current['Id']==prior['Id'] and current['Image']==prior['Image'] and current['State']['Pid']==prior['State']['Pid']
   assert current['Config']==prior['Config'] and current['HostConfig']==prior['HostConfig']
assert all(c['State']['Running'] and c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' for c in before.values())
def save(name,data):
 p=work/name
 if p.exists():
  assert RESUME and p.read_bytes()==data;return
 with p.open('xb') as stream:os.chmod(p,0o600);stream.write(data);stream.flush();os.fsync(stream.fileno())
save('containers-before.json',json.dumps(before).encode())
configs={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('compose.yaml','compose.override.yaml','config/leroy.toml','config/controller.env','config/runner.toml')}
for name in configs:save(name.replace('/','-')+'.before',(root/name).read_bytes())
if not RESUME:
 with (work/'database-before.dump').open('xb') as output:
  os.chmod(work/'database-before.dump',0o600)
  r=subprocess.run(['docker','exec',before['postgres']['Id'],'pg_dump','-U','leroy','-d','leroy','-Fc'],stdout=output,stderr=subprocess.PIPE,timeout=120)
  assert r.returncode==0,'Protected database backup failed';output.flush();os.fsync(output.fileno())
assert (work/'database-before.dump').read_bytes()[:5]==b'PGDMP'
backup_sha=hashlib.sha256((work/'database-before.dump').read_bytes()).hexdigest()
counts=lambda:call(['docker','exec',before['postgres']['Id'],'psql','-XqAt','-U','leroy','-d','leroy','-c',
 'SELECT json_build_object(\'runs\',(SELECT count(*) FROM runs),\'steps\',(SELECT count(*) FROM steps),\'artifacts\',(SELECT count(*) FROM artifacts))']).strip()
with (work/'database-before.dump').open('rb') as source:
 restored=subprocess.run(['docker','exec','-i',before['postgres']['Id'],'pg_restore','--data-only','--file=-'],stdin=source,capture_output=True,timeout=60)
assert restored.returncode==0,'Could not inspect protected backup; no restore executed'
backup_counts={};table=None
for line in restored.stdout.decode().splitlines():
 match=re.match(r'^COPY public\."?(runs|steps|artifacts)"? \(',line)
 if match:table=match[1];backup_counts[table]=0
 elif table is not None:
  if line=='\\.':table=None
  else:backup_counts[table]+=1
assert set(backup_counts)=={'runs','steps','artifacts'}
save('counts-from-backup.json',json.dumps(backup_counts).encode())
counts_before=json.dumps(backup_counts).encode()
old=before['controller'];alias=old['Config']['Image'];assert alias.startswith('leroy-controller:')
assert old['Image']==QUALIFIED_CONTROLLER_BEFORE
code="import pathlib,hashlib,json,leroy;p=pathlib.Path(leroy.__file__).parent/'engine.py';print(json.dumps({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))"
live_controller=inspect('leroy-nas-parity-controller-1')
module=json.loads(call(['docker','exec',live_controller['Id'],'python','-c',code]))
assert module['sha256']==(NEW_SHA if VERIFY_APPLIED else OLD_SHA)
assert module['path'].startswith('/usr/local/lib/python3.') and module['path'].endswith('/site-packages/leroy/engine.py')
with tarfile.open(root/'reconcile-engine-20261014.tar') as bundle:
 members=bundle.getmembers();assert len(members)==1 and members[0].name=='engine.py' and members[0].isfile()
 data=bundle.extractfile(members[0]).read();assert hashlib.sha256(data).hexdigest()==NEW_SHA
(work/'engine.py').write_bytes(data)
base='leroy-controller:before-reconcile-locks-20261014'
image=json.loads(call(['docker','image','inspect',QUALIFIED_IMAGE]))[0];original=json.loads(call(['docker','image','inspect',old['Image']]))[0]
assert json.loads(call(['docker','image','inspect',base]))[0]['Id']==original['Id']
assert image['Config']==original['Config'] and image['RootFS']['Layers'][:-1]==original['RootFS']['Layers']
probe=json.loads(call(['docker','run','--rm','--network','none','--memory','128m','--memory-swap','128m',QUALIFIED_IMAGE,'python','-c',code],timeout=60))
assert probe['sha256']==NEW_SHA
if not VERIFY_APPLIED:
 call(['docker','tag',image['Id'],alias])
 call(['docker','compose','up','-d','--no-deps','--no-build','--pull','never','controller'],cwd=root,timeout=180)
deadline=time.monotonic()+60
while True:
 try:
  with urllib.request.urlopen('http://192.168.178.97:8088/health/ready',timeout=3) as response:assert response.status==200
  break
 except Exception:
  assert time.monotonic()<deadline,'API readiness deadline; retain deployment journal'
  time.sleep(2)
current=inspect('leroy-nas-parity-controller-1');assert current['Image']==image['Id'] and current['State']['Running']
for name in ('Env','Cmd','Entrypoint','User','WorkingDir'):
 assert (sorted(current['Config'][name])==sorted(old['Config'][name]) if name=='Env' else current['Config'].get(name)==old['Config'].get(name))
for name in ('Memory','MemorySwap','NanoCpus','MemoryReservation','CgroupParent','NetworkMode','RestartPolicy','LogConfig','Dns'):assert current['HostConfig'].get(name)==old['HostConfig'].get(name)
mounts=lambda c:sorted([{k:m[k] for k in ('Type','Source','Destination','RW')} for m in c['Mounts']],key=lambda m:m['Destination'])
assert mounts(current)==mounts(old)
assert json.loads(call(['docker','exec',current['Id'],'python','-c',code]))['sha256']==NEW_SHA
for service in ('postgres','runner','docker'):
 now=inspect('leroy-nas-parity-'+service+'-1');prior=before[service]
 assert now['Id']==prior['Id'] and now['Image']==prior['Image'] and now['State']['Pid']==prior['State']['Pid']
assert configs=={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in configs}
assert json.loads(counts())==backup_counts
save('controller-after.json',json.dumps(current).encode())
print(json.dumps({'controller_before_image':old['Image'],'controller_image':image['Id'],'engine_sha256':NEW_SHA,
 'only_engine_module_replaced':True,'image_configuration_unchanged':True,'base_layers_preserved':True,
 'exact_postgres_qualified_image_deployed':image['Id']==QUALIFIED_IMAGE,
 'protected_database_backup_sha256':backup_sha,'run_step_artifact_counts_preserved':json.loads(counts_before),
 'controller_resources_environment_and_mounts_unchanged':True,'postgres_runner_daemon_processes_unchanged':True,
 'configuration_files_unchanged':True,'lease_deadlines_or_fencing_changed':False,
 'graphato_source_or_tests_changed':False,'production_modified':False}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resume-prepared', action='store_true')
    parser.add_argument('--verify-applied', action='store_true')
    args = parser.parse_args()
    assert args.apply
    folder = ROOT / 'test-results/nas-parity/followup/controller-reconcile-locks-20261014'
    proof = json.loads((folder / 'postgres-validation.json').read_text())
    source = ROOT / 'src/leroy/engine.py'
    assert proof['all_passed'] and proof['postgres_tests'] >= 34 and proof['original_counterexamples'] == 2
    assert proof['engine_sha256'] == vm.digest(source)
    cleanup = json.loads((folder / 'postgres-cleanup.json').read_text())
    assert cleanup['ephemeral_database_removed'] and cleanup['ephemeral_network_removed']
    marker = folder / 'deployment-start.json'
    assert not (folder / 'deployment-proof.json').exists(), 'Retain completed deployment evidence'
    resume = args.resume_prepared or args.verify_applied
    assert resume == marker.exists(), 'Inspect any uncertain deployment before explicitly resuming'
    idle()
    assert not vm.state()['State']['Running']
    if marker.exists():
        retained = json.loads(marker.read_text())
        assert retained['engine_sha256'] == vm.digest(source)
        guard = retained['production_guard_before']
    else:
        guard = begin(folder, 'reconcile-lock-deployment')
        marker.write_text(json.dumps({'production_guard_before': guard, 'engine_sha256': vm.digest(source)}) + '\n')
    archive = folder / 'reconcile-engine-20261014.tar'
    with tarfile.open(archive, 'w') as bundle:
        bundle.add(source, arcname='engine.py')
    upload_file(archive, '/volume1/docker/leroy-nas-parity/' + archive.name, vm.CREDENTIALS)
    code = ('OLD_SHA=' + repr(proof['engine_before_sha256']) + '\nNEW_SHA=' + repr(vm.digest(source)) +
            '\nQUALIFIED_IMAGE=' + repr(proof['candidate_image']) +
            '\nQUALIFIED_CONTROLLER_BEFORE=' + repr(proof['controller_before_image']) +
            '\nRESUME=' + repr(resume) + '\nVERIFY_APPLIED=' + repr(args.verify_applied) + '\n')
    result = json.loads(vm.remote(code + PROGRAM, sudo=True, timeout=600))
    (folder / 'deployment-proof.json').write_text(json.dumps(result, indent=2) + '\n')
    finish(folder, 'reconcile-lock-deployment', guard)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
