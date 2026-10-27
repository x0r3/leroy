"""Move only the idle, owned NAS test control plane to existing SSD storage.

Keep the original volumes, a logical backup and byte-verified physical copies.
Never change Graphato, CI images, durability, lease budgets or production data.
An uncertain or partial outcome requires inspection, not an automatic retry.
"""

import argparse
import json
from contextlib import closing
from datetime import datetime, timezone

import nas_release_vm as vm
from compare_nas_antares import client
from nas_followup_support import inner
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT

PROGRAM = r'''
import hashlib,json,os,pathlib,re,shutil,stat,subprocess,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert root.resolve()==root and (root/'.leroy-owned').is_file()
destination=pathlib.Path('/overlay/leroy-nas-parity-control-test/20261011')
parent=destination.parent
assert parent.resolve()==parent and not parent.is_symlink()
if RESUME_COPY:
 assert destination.is_dir() and destination.resolve()==destination and not destination.is_symlink()
 assert (destination/'.leroy-owned').read_text()=='Leroy isolated control plane storage only\n'
 retained=json.loads((destination/'progress.json').read_text())
 assert retained['phase']=='original-database-stopped-and-backed-up', 'Only the inspected copy failure can resume'
else:
 assert not destination.exists(), 'Previous outcome must be inspected before resuming'
override=root/'compose.override.yaml'
assert not override.exists(), 'Preserve any existing Compose override'
def run(args, timeout=60):
 return subprocess.check_output(args,text=True,timeout=timeout)
def inspect(name):
 item=json.loads(run(['docker','inspect',name]))[0]
 assert item['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
 return item
old={service:inspect('leroy-nas-parity-'+service+'-1') for service in ('postgres','controller','runner')}
configuration_paths=[root/'compose.yaml',root/'config/leroy.toml',root/'config/runner.toml',root/'config/controller.env']
configuration_hashes={path.relative_to(root).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in configuration_paths}
if RESUME_COPY:
 assert all(not item['State']['Running'] for item in old.values())
 assert all(item['Image']==retained['previous_images'][service] for service,item in old.items())
else:
 assert all(item['State']['Running'] for item in old.values())
target=json.loads(run(['docker','inspect','leroy-nas-release-target-vm']))[0]
assert target['Config']['Labels']['io.leroy.nas-release-target']=='0ad540dd578033d45e4d0c25d89fbe57b32102a4'
assert not target['State']['Running']
outer=inspect('leroy-nas-parity-docker-1')
prefix=['docker','exec',outer['Id'],'docker']
assert run(prefix+['inspect','jenkins-parity','--format','{{.State.Running}}']).strip()=='false'
assert not run(prefix+['ps','--filter','label=io.leroy.runner=runner-nas-parity','-q']).strip()
parent_marker=parent/'.leroy-owned'
if parent.exists():
 assert parent.is_dir() and parent.stat().st_uid==0
 assert parent_marker.is_file() and not parent_marker.is_symlink()
 assert parent_marker.read_text()=='Leroy isolated control plane storage only\n'
else:
 parent.mkdir(mode=0o700)
 parent_marker.write_text('Leroy isolated control plane storage only\n');parent_marker.chmod(0o600)
parent.chmod(0o700)
mount=json.loads(run(['findmnt','-J','-T',str(parent),'-o','SOURCE,FSTYPE,TARGET']))['filesystems'][0]
assert mount['source']=='/dev/nvme0n1p7' and mount['fstype']=='ext4' and mount['target']=='/overlay'
if RESUME_COPY:
 evidence=destination/'copy-failure-progress.json';assert not evidence.exists()
 shutil.copy2(destination/'progress.json',evidence)
 state=retained
 state['copy_failure_recovery']={'at':time.time(),'reason':'Copy callback received a string path; original volumes preserved'}
else:
 destination.mkdir(mode=0o700)
 (destination/'.leroy-owned').write_text('Leroy isolated control plane storage only\n')
 os.chmod(destination/'.leroy-owned',0o600)
 state={'started_at':time.time(),'production_modified':False,'original_volumes_retained':True,
  'ssd_mount':mount,'previous_images':{service:item['Image'] for service,item in old.items()}}
state['configuration_hashes_before_physical_copy']=configuration_hashes
def record(phase):
 state['phase']=phase
 path=destination/'progress.json';temporary=destination/'progress.json.tmp'
 with temporary.open('w') as stream:
  stream.write(json.dumps(state,indent=2)+'\n');stream.flush();os.fsync(stream.fileno())
 temporary.chmod(0o600);temporary.replace(path)
 fd=os.open(destination,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
record('validated-owned-copy-recovery' if RESUME_COPY else 'validated-owned-idle-stack')
docker_root=pathlib.Path(json.loads(run(['docker','info','--format','{{json .DockerRootDir}}']))).resolve(strict=True)
sources={}
for service,volume,target_mount in (('postgres','database','/var/lib/postgresql'),('controller','data','/data')):
 mount_item,=(entry for entry in old[service]['Mounts'] if entry['Destination']==target_mount)
 assert mount_item['Type']=='volume' and mount_item['Name']=='leroy-nas-parity_'+volume
 item=json.loads(run(['docker','volume','inspect',mount_item['Name']]))[0]
 assert item['Labels']['com.docker.compose.project']=='leroy-nas-parity'
 assert item['Labels']['com.docker.compose.volume']==volume
 source=pathlib.Path(item['Mountpoint']).resolve(strict=True)
 assert source==pathlib.Path(mount_item['Source']).resolve(strict=True) and source.is_relative_to(docker_root/'volumes')
 sources[service]=source
state['original_volume_names']={key:'leroy-nas-parity_'+('database' if key=='postgres' else 'data') for key in sources}
estimated_size=sum(path.stat().st_size for source in sources.values() for path in source.rglob('*') if path.is_file())
assert estimated_size<=4*1024**3, 'Review a larger copy while the original stack is still running'
assert shutil.disk_usage(destination).free>=40*1024**3+estimated_size+1024**3
state['estimated_copy_bytes']=estimated_size
compose=['docker','compose','-f',str(root/'compose.yaml')]
if not RESUME_COPY:
 subprocess.run(compose+['stop','--timeout','60','runner','controller'],cwd=root,check=True,stdout=subprocess.DEVNULL,timeout=150)
 record('controller-and-runner-stopped')
def query(sql):
 return run(['docker','exec','-e','PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=20000',
  'leroy-nas-parity-postgres-1','psql','-X','-qAt','-U','leroy','-d','leroy','-c',sql],timeout=45)
def fingerprint():
 tables=json.loads(query("SELECT json_agg(tablename ORDER BY tablename) FROM pg_tables WHERE schemaname='public'"))
 assert tables and all(re.fullmatch('[a-z_]+',table) for table in tables)
 unions=[]
 for table in tables:
  unions.append("SELECT '"+table+"' AS table_name,count(*) AS row_count,"
   "md5(coalesce(string_agg(row_to_json(t)::text,E'\\n' ORDER BY row_to_json(t)::text),'')) AS content_hash FROM public.\""+table+"\" t")
 return json.loads(query("SELECT json_agg(f ORDER BY table_name) FROM ("+' UNION ALL '.join(unions)+') f'))
backup=destination/'database-before.dump'
if RESUME_COPY:
 with backup.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==state['logical_backup_sha256']
 assert state['logical_tables_before']
else:
 state['logical_tables_before']=fingerprint()
 with backup.open('xb') as stream:
  subprocess.run(['docker','exec','leroy-nas-parity-postgres-1','pg_dump','-U','leroy','-d','leroy','-Fc'],
   stdout=stream,check=True,timeout=120)
  stream.flush();os.fsync(stream.fileno())
 backup.chmod(0o600)
 with backup.open('rb') as stream:state['logical_backup_sha256']=hashlib.file_digest(stream,'sha256').hexdigest()
 subprocess.run(compose+['stop','--timeout','60','postgres'],cwd=root,check=True,stdout=subprocess.DEVNULL,timeout=90)
assert not inspect('leroy-nas-parity-postgres-1')['State']['Running']
assert inspect('leroy-nas-parity-postgres-1')['State']['ExitCode']==0, 'Retain and inspect an unclean original database shutdown'
record('original-database-stopped-and-backed-up')
def inventory(base):
 files={};size=0
 for path in sorted(base.rglob('*')):
  mode=path.lstat().st_mode
  assert stat.S_ISREG(mode) or stat.S_ISDIR(mode), 'Do not follow links or special files'
  assert path.resolve().is_relative_to(base)
  if path.is_file():
   with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
   info=path.stat();relative=path.relative_to(base).as_posix()
   files[relative]={'sha256':digest,'size':info.st_size,'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(mode)}
   size+=info.st_size
 return {'files':files,'bytes':size}
manifests={service:inventory(source) for service,source in sources.items()}
total=sum(value['bytes'] for value in manifests.values())
assert total<=4*1024**3, 'Review a larger copy before moving the test stack'
assert shutil.disk_usage(destination).free>=40*1024**3+total+1024**3
def preserve_owner(source,target):
 source=pathlib.Path(source);target=pathlib.Path(target)
 shutil.copy2(source,target,follow_symlinks=False)
 info=source.stat();os.chown(target,info.st_uid,info.st_gid)
 fd=os.open(target,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
 return str(target)
for service,source in sources.items():
 copied=destination/service
 if copied.exists():
  assert RESUME_COPY and copied.resolve()==copied and not copied.is_symlink()
  partial=inventory(copied)
  assert partial['files'].keys()<=manifests[service]['files'].keys()
  assert all(row['sha256']==manifests[service]['files'][name]['sha256'] and row['size']==manifests[service]['files'][name]['size'] for name,row in partial['files'].items())
  assert all((source/path.relative_to(copied)).is_dir() for path in copied.rglob('*') if path.is_dir())
 shutil.copytree(source,copied,copy_function=preserve_owner,symlinks=False,dirs_exist_ok=RESUME_COPY)
 for original in [source,*[path for path in source.rglob('*') if path.is_dir()]]:
  info=original.stat();path=copied/original.relative_to(source)
  os.chown(path,info.st_uid,info.st_gid);os.chmod(path,stat.S_IMODE(info.st_mode))
  after=path.stat();assert (after.st_uid,after.st_gid,stat.S_IMODE(after.st_mode))==(info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))
  fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(fd)
  finally:os.close(fd)
 assert inventory(copied)==manifests[service]
state['physical_copy_bytes']=total
state['physical_manifests_sha256']={service:hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest() for service,value in manifests.items()}
state['physical_copies_byte_and_ownership_verified']=True
record('physical-copies-verified')
content={'services':{'postgres':{'volumes':[{'type':'bind','source':str(destination/'postgres'),'target':'/var/lib/postgresql'}]},
 'controller':{'volumes':[{'type':'bind','source':str(destination/'controller'),'target':'/data'}]}}}
staged=root/'compose.control-ssd-20261011.yaml'
assert not staged.exists();staged.write_text(json.dumps(content,indent=2)+'\n');staged.chmod(0o600)
expanded=json.loads(run(compose+['-f',str(staged),'config','--format','json']))
for service,target_mount in (('postgres','/var/lib/postgresql'),('controller','/data')):
 binding,=(item for item in expanded['services'][service]['volumes'] if item['target']==target_mount)
 assert binding['type']=='bind' and binding['source']==str(destination/service)
for service in old:assert expanded['services'][service]['image']==old[service]['Config']['Image']
staged.rename(override)
state['compose_override_sha256']=hashlib.sha256(override.read_bytes()).hexdigest()
record('owned-compose-storage-override-installed')
new_compose=['docker','compose','-f',str(root/'compose.yaml'),'-f',str(override)]
subprocess.run(new_compose+['up','-d','--pull','never','--no-deps','--wait','--wait-timeout','120','postgres'],cwd=root,check=True,stdout=subprocess.DEVNULL,timeout=180)
state['logical_tables_after']=fingerprint()
assert state['logical_tables_after']==state['logical_tables_before']
record('restored-database-logical-content-verified')
subprocess.run(new_compose+['up','-d','--pull','never','--no-deps','--wait','--wait-timeout','120','controller','runner'],cwd=root,check=True,stdout=subprocess.DEVNULL,timeout=180)
for service,item in old.items():
 current=inspect('leroy-nas-parity-'+service+'-1')
 assert current['Image']==item['Image'] and current['State']['Running']
 for field in ('Env','Cmd','Entrypoint','User','WorkingDir'):
  assert current['Config'][field]==item['Config'][field], 'Runtime setting changed during storage migration'
 if service in sources:
  expected='/var/lib/postgresql' if service=='postgres' else '/data'
  binding,=(entry for entry in current['Mounts'] if entry['Destination']==expected)
  assert binding['Type']=='bind' and binding['Source']==str(destination/service)
assert configuration_hashes=={path.relative_to(root).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in configuration_paths}
state.update(completed_at=time.time(),same_images=True,logical_content_verified=True,
 original_configuration_hashes=configuration_hashes,same_runtime_settings=True,
 graphato_sources_or_tests_changed=False,lease_budgets_changed=False,durability_disabled=False)
record('completed')
print(json.dumps(state))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Apply the reviewed migration after the original CI attempts are idle')
    parser.add_argument('--resume-copy', action='store_true', help='Recover only the inspected, backed-up copy callback failure')
    args = parser.parse_args()
    assert args.apply != args.resume_copy, 'Select one explicit operation; importing makes no NAS changes'
    folder = ROOT / 'test-results/nas-parity/followup/control-storage-ssd-20261011'
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / 'started.json'
    assert marker.exists() == args.resume_copy, 'Inspect an uncertain previous outcome before any retry'
    assert not vm.state()['State']['Running']
    assert inner('inspect', 'jenkins-parity', '--format', '{{.State.Running}}').strip() == 'false'
    if not args.resume_copy:
        with closing(client()) as api:
            for status in ('queued', 'running', 'waiting'):
                reply = api.get('/api/runs', params={'status': status})
                reply.raise_for_status()
                assert not reply.json()
            reply = api.get('/api/pipelines')
            reply.raise_for_status()
            assert not any(row['enabled'] for row in reply.json())
    if args.resume_copy:
        recovery_marker = folder / 'copy-recovery-started.json'
        assert not recovery_marker.exists(), 'Inspect any uncertain recovery before another attempt'
        recovery_phase = begin(folder, 'control-storage-copy-recovery')
        recovery_marker.write_text(json.dumps({'at': datetime.now(timezone.utc).isoformat(),
                                              'production_guard_before': recovery_phase}) + '\n')
        phase = json.loads(marker.read_text())['production_guard_before']
    else:
        phase = begin(folder, 'control-storage-migration')
        marker.write_text(json.dumps({'at': datetime.now(timezone.utc).isoformat(),
                                     'production_guard_before': phase}) + '\n')
    proof = json.loads(vm.remote('RESUME_COPY=' + repr(args.resume_copy) + '\n' + PROGRAM, sudo=True, timeout=900))
    (folder / 'storage-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    with closing(client()) as api:
        response = api.get('/health/ready')
        response.raise_for_status()
        assert response.json()['status'] == 'ok'
    finish(folder, 'control-storage-migration', phase)
    if args.resume_copy:
        finish(folder, 'control-storage-copy-recovery', recovery_phase)
    print(json.dumps({'migration_completed': True, 'physical_copy_bytes': proof['physical_copy_bytes'],
                      'same_images': proof['same_images'], 'logical_content_verified': True,
                      'original_volumes_retained': True, 'production_modified': False}))


if __name__ == '__main__':
    main()
