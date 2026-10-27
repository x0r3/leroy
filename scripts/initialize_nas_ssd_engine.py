"""Seed an idle, owned SSD test engine; retain the complete old HDD engine.

Only the current Gitea/private Jenkins root filesystems and the qualified worker
are transferred. Existing named volumes remain on their original storage. The
native Jenkins, NAS applications, controller and PostgreSQL are never restarted.
"""

import json

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT

BASE = ROOT / 'test-results/nas-parity/followup'
WORKER = 'sha256:1facfe12a4ea704a616ff87bbcab16e4bdc6775390b74904ac2a299579749035'

PROGRAM = r'''
import copy,hashlib,http.client,json,os,pathlib,re,shutil,socket,subprocess,tarfile,time,urllib.parse,xml.etree.ElementTree as ET
owner=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (owner/'.leroy-owned').is_file()
work=pathlib.Path('/overlay/leroy-nas-parity-engine-test')/DAY
assert work.parent.parent==pathlib.Path('/overlay') and work.parent.resolve()==work.parent
work.parent.mkdir(exist_ok=True,mode=0o700);assert work.parent.stat().st_uid==0
if RESUME_EXPORT:
 retained=json.loads((work/'state.json').read_text());recovery=json.loads((work/'manual-recovery.json').read_text())
 assert retained['phase']=='failed:AssertionError' and recovery['all_seven_healthy'] and recovery['runner_running']
 assert recovery['messages_present']['Daemon shutdown complete']
 resume_record=work/('state-before-export-resume-'+str(RESUME_SEQUENCE)+'.json')
 assert not resume_record.exists()
 resume_record.write_bytes((work/'state.json').read_bytes());resume_record.chmod(0o600)
else:
 assert not work.exists();work.mkdir(mode=0o700)
engine=work/'engine'
if RESUME_EXPORT:
 assert engine.is_dir() and engine.resolve()==engine and engine.stat().st_uid==0
 if (engine/'containers').exists():
  saved_snapshots=json.loads((work/'source-snapshots.json').read_text())
  for p in (engine/'containers').iterdir():
   assert p.is_dir() and not p.is_symlink()
   c=json.loads((p/'config.v2.json').read_text());name=c['Name'].lstrip('/')
   assert name in saved_snapshots and c['Config']['Image']==saved_snapshots[name]['image']
   assert c['Config']['Labels'].get('io.leroy.nas-parity')=='true'
else:engine.mkdir(mode=0o700)
assert json.loads(subprocess.check_output(['findmnt','-J','-T',str(work),'-o','SOURCE,FSTYPE,TARGET']))['filesystems'][0]=={'source':'/dev/nvme0n1p7','fstype':'ext4','target':'/overlay'}
assert shutil.disk_usage(work).free>=65*1024**3
def call(args,timeout=30,**kw):
 r=subprocess.run(args,capture_output=True,timeout=timeout,**kw)
 if r.returncode:
  p=work/'failed-command.json';p.write_text(json.dumps({'at_epoch':time.time(),'operation':args[:2],
   'arguments_sha256':hashlib.sha256(json.dumps(args).encode()).hexdigest(),'exit_code':r.returncode,
   'stderr':r.stderr.decode(errors='replace')[-8000:]},indent=2)+'\n');p.chmod(0o600)
  raise AssertionError('Owned SSD engine operation failed; inspect its protected journal')
 return r.stdout
def inspect(name):return json.loads(call(['docker','inspect',name]))[0]
def sha(data):return hashlib.sha256(data).hexdigest()
def save(name,value):
 p=work/name;t=p.with_suffix(p.suffix+'.pending');assert not t.exists()
 with t.open('x') as f:
  os.chmod(t,0o600);json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 t.replace(p);fd=os.open(p.parent,os.O_DIRECTORY|os.O_RDONLY);os.fsync(fd);os.close(fd)
def atomic(path,data):
 st=path.stat();t=path.with_suffix(path.suffix+'.ssd-pending');assert not t.exists()
 with t.open('xb') as f:
  os.chmod(t,st.st_mode&0o777);os.chown(t,st.st_uid,st.st_gid);f.write(data);f.flush();os.fsync(f.fileno())
 t.replace(path);fd=os.open(path.parent,os.O_DIRECTORY|os.O_RDONLY);os.fsync(fd);os.close(fd)
services={n:inspect('leroy-nas-parity-'+n+'-1') for n in ('controller','postgres','runner','docker')}
assert all(c['State']['Running'] and c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' for c in services.values())
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
for c in json.loads(call(['docker','inspect','paperless','sonarr','radarr','sabnzbd','plex','yt-downloader-service','mail-ingest-service'])):
 assert c['State']['Running'] and c['State'].get('Health',{}).get('Status') in (None,'healthy')
outer=services['docker'];old_root=pathlib.Path(next(m['Source'] for m in outer['Mounts'] if m['Destination']=='/var/lib/docker'))
assert old_root==pathlib.Path('/volume1/@docker/volumes/leroy-nas-parity_engine/_data') and old_root.resolve()==old_root
volume=json.loads(call(['docker','volume','inspect','leroy-nas-parity_engine']))[0]
assert volume['Labels']['com.docker.compose.project']=='leroy-nas-parity' and volume['Labels']['com.docker.compose.volume']=='engine'
class UnixHTTP(http.client.HTTPConnection):
 def __init__(self,pid):super().__init__('localhost',timeout=90);self.path='/proc/'+str(pid)+'/root/run/docker.sock'
 def connect(self):
  self.sock=socket.socket(socket.AF_UNIX);self.sock.settimeout(90);self.sock.connect(self.path)
def api(pid,method,path,body=None,expected=(200,201,204)):
 c=UnixHTTP(pid)
 try:
  c.request(method,path,None if body is None else json.dumps(body).encode(),{} if body is None else {'Content-Type':'application/json'})
  r=c.getresponse();data=r.read();assert r.status in expected,'Owned Docker API operation rejected; output withheld'
  return json.loads(data) if data else None
 finally:c.close()
oldpid=outer['State']['Pid'];prefix=['docker','exec',outer['Id'],'docker']
identity=api(oldpid,'GET','/info')
assert identity['DockerRootDir']=='/var/lib/docker' and identity['ID']==json.loads(call(prefix+['info','--format','{{json .ID}}']))
assert not call(prefix+['ps','-aq','--filter','label=io.leroy.runner=runner-nas-parity']).strip()
specs={name:api(oldpid,'GET','/containers/'+name+'/json') for name in ('gitea','jenkins-parity')}
assert specs['gitea']['State']['Running'] and not specs['jenkins-parity']['State']['Running']
assert all(c['Config']['Labels'].get('io.leroy.nas-parity')=='true' for c in specs.values())
assert all(not c['HostConfig'].get('Links') and not c['HostConfig'].get('VolumesFrom') for c in specs.values())
net=api(oldpid,'GET','/networks/leroy-jobs')
assert all(set(c['NetworkSettings']['Networks'])=={'leroy-jobs'} for c in specs.values())
if RESUME_EXPORT:
 saved=json.loads((work/'source-containers.json').read_text())
 assert all(specs[n]['Config']==c['Config'] and specs[n]['HostConfig']==c['HostConfig'] and specs[n]['Image']==c['Image'] for n,c in saved.items())
else:save('source-containers.json',specs);save('source-network.json',net)
cfg=owner/'compose.override.yaml';before=cfg.read_bytes();save('override-before.json',json.loads(before))
compose=['docker','compose','--project-directory',str(owner),'-p','leroy-nas-parity','-f',str(owner/'compose.yaml'),'-f',str(cfg)]
canonical_before=json.loads(call(compose+['config','--format','json']))
profile_sha=sha((owner/'config/runner.toml').read_bytes())
native=inspect('jenkins');home=pathlib.Path(next(m['Source'] for m in native['Mounts'] if m['Destination']=='/var/jenkins_home'))
def checkpoint():
 mem={s.split(':')[0]:int(s.split()[1]) for s in pathlib.Path('/proc/meminfo').read_text().splitlines() if s.startswith(('MemAvailable:','SwapFree:'))}
 assert mem['MemAvailable']>=128*1024 and mem['SwapFree']>=2304*1024
 assert shutil.disk_usage(work).free>=40*1024**3+12*1024**3
 for name,row in PRODUCTION.items():
  p=home/'jobs'/name;n=int((p/'nextBuildNumber').read_text())-1 if (p/'nextBuildNumber').exists() else 0
  assert n==row['number']
  if n:assert ET.parse(p/'builds'/str(n)/'build.xml').getroot().findtext('completed')=='true'
checkpoint();state={'phase':'prepared','old_root':str(old_root),'new_root':str(engine),'old_daemon_id':outer['Id'],
 'source_container_ids':{n:c['Id'] for n,c in specs.items()},'worker_image':WORKER,'old_root_retained':True}
save('state.json',state);switched=False;runner_stopped=False;gitea_stopped=False;result=None
try:
 api(oldpid,'POST','/containers/gitea/stop?t=45');gitea_stopped=True
 snapshots=json.loads((work/'source-snapshots.json').read_text()) if RESUME_EXPORT else {}
 for name,c in ([] if RESUME_EXPORT else specs.items()):
  tag='leroy-acceptance:'+('gitea' if name=='gitea' else 'jenkins')+'-rootfs-'+DAY
  assert subprocess.run(prefix+['image','inspect',tag],capture_output=True).returncode!=0
  repo,version=tag.rsplit(':',1)
  snapshot=api(oldpid,'POST','/commit?'+urllib.parse.urlencode({'container':c['Id'],'repo':repo,'tag':version,'pause':'false'}))['Id']
  assert re.fullmatch('sha256:[a-f0-9]{64}',snapshot)
  image=api(oldpid,'GET','/images/'+snapshot+'/json');base=api(oldpid,'GET','/images/'+c['Image']+'/json')
  assert image['RootFS']['Layers'][:len(base['RootFS']['Layers'])]==base['RootFS']['Layers']
  snapshots[name]={'image':snapshot,'base_image':c['Image'],'rootfs':image['RootFS'],'config':image['Config']}
 worker=api(oldpid,'GET','/images/'+WORKER+'/json')
 if not RESUME_EXPORT:save('source-snapshots.json',snapshots)
 transfer=work/'selected-images.tar'
 if not RESUME_EXPORT:
  with transfer.open('xb') as f:
   os.chmod(transfer,0o600)
   p=subprocess.Popen(prefix+['save',WORKER,*[s['image'] for s in snapshots.values()]],stdout=f,stderr=subprocess.PIPE)
   try:
    deadline=time.monotonic()+600
    while p.poll() is None:checkpoint();assert time.monotonic()<deadline;time.sleep(3)
    assert p.returncode==0,'Selected image export failed; error output withheld'
   finally:
    if p.poll() is None:p.terminate();p.wait(timeout=20)
   f.flush();os.fsync(f.fileno())
 with transfer.open('rb') as f:transfer_sha=hashlib.file_digest(f,'sha256').hexdigest()
 checkpoint();call(['docker','stop','--time','30',services['runner']['Id']],timeout=50);runner_stopped=True
 def shutdown_marker():
  r=subprocess.run(['docker','logs','--tail','1000',outer['Id']],capture_output=True,timeout=20)
  assert r.returncode==0
  lines=[line for line in (r.stdout+b'\n'+r.stderr).splitlines() if b'Daemon shutdown complete' in line]
  return sha(lines[-1]) if lines else None
 prior_shutdown=shutdown_marker()
 call(['docker','stop','--time','90',outer['Id']],timeout=120)
 stopped=inspect(outer['Id']);assert not stopped['State']['Running'] and not stopped['State']['OOMKilled']
 completed_shutdown=shutdown_marker()
 # Check the daemon's own new completion marker, independent of wrapper exit
 # status and client/server clock differences. No arbitrary log text is saved.
 assert completed_shutdown is not None and completed_shutdown!=prior_shutdown
 save('daemon-stop.json',{'exit_code':stopped['State']['ExitCode'],'oom_killed':False,
  'daemon_shutdown_completed':True,'before_marker_sha256':prior_shutdown,'completed_marker_sha256':completed_shutdown})
 override=json.loads(before);override.setdefault('services',{}).setdefault('docker',{}).setdefault('volumes',[])
 assert not override['services']['docker']['volumes']
 override['services']['docker']['volumes']=[
  {'type':'bind','source':str(engine),'target':'/var/lib/docker','bind':{'create_host_path':False}},
  {'type':'bind','source':str(old_root/'volumes'),'target':'/var/lib/docker/volumes','bind':{'create_host_path':False}},
  {'type':'volume','source':'engine','target':'/legacy-engine','read_only':True}]
 atomic(cfg,(json.dumps(override,indent=2)+'\n').encode());switched=True
 canonical_after=json.loads(call(compose+['config','--format','json']))
 def mask(value):
  c=copy.deepcopy(value);c['services']['docker']['volumes']=sorted([m for m in c['services']['docker']['volumes'] if m['target'] not in ('/var/lib/docker','/var/lib/docker/volumes','/legacy-engine')],key=lambda m:m['target']);return c
 assert mask(canonical_before)==mask(canonical_after),'Unrelated Compose configuration changed'
 state['phase']='new_root_selected';save('state.json',state)
 call(compose+['up','-d','--no-deps','--no-build','--pull','never','docker'],timeout=120)
 current=inspect('leroy-nas-parity-docker-1');assert current['Image']==outer['Image'] and current['State']['Running']
 newpid=current['State']['Pid'];prefix=['docker','exec',current['Id'],'docker']
 for _ in range(60):
  try:
   current=inspect('leroy-nas-parity-docker-1');newpid=current['State']['Pid'];api(newpid,'GET','/version');break
  except (OSError,AssertionError,http.client.HTTPException):time.sleep(1)
 else:raise RuntimeError('New owned engine not ready')
 retained_containers=api(newpid,'GET','/containers/json?all=1')
 assert all(row['State'] in ('created','exited') and set(row['Names']) <= {'/gitea','/jenkins-parity'} for row in retained_containers)
 with transfer.open('rb') as f:call(['docker','exec','-i',current['Id'],'docker','load'],stdin=f,timeout=600)
 loaded=api(newpid,'GET','/images/'+WORKER+'/json');assert loaded['Id']==WORKER and loaded['RootFS']==worker['RootFS'] and loaded['Config']==worker['Config']
 network={k:net[k] for k in ('Name','Driver','Internal','Attachable','EnableIPv6','IPAM','Options','Labels')}
 if 'EnableIPv4' in net:network['EnableIPv4']=net['EnableIPv4']
 network['CheckDuplicate']=True
 networks=api(newpid,'GET','/networks')
 if not any(n['Name']=='leroy-jobs' for n in networks):api(newpid,'POST','/networks/create',network)
 actual_network=api(newpid,'GET','/networks/leroy-jobs')
 assert all(actual_network[k]==v for k,v in network.items() if k!='CheckDuplicate')
 created={}
 for name,c in specs.items():
  snapshot=snapshots[name];image=api(newpid,'GET','/images/'+snapshot['image']+'/json')
  assert image['RootFS']==snapshot['rootfs'] and image['Config']==snapshot['config']
  expected_host=copy.deepcopy(c['HostConfig'])
  if expected_host.get('OomKillDisable') is None:expected_host['OomKillDisable']=False
  body=copy.deepcopy(c['Config']);body['Image']=snapshot['image'];body['HostConfig']=expected_host
  endpoint=c['NetworkSettings']['Networks']['leroy-jobs']
  body['NetworkingConfig']={'EndpointsConfig':{'leroy-jobs':{k:endpoint[k] for k in ('IPAMConfig','Aliases','Links','DriverOpts') if k in endpoint}}}
  existing=next((row for row in retained_containers if '/'+name in row['Names']),None)
  identity=existing['Id'] if existing else api(newpid,'POST','/containers/create?name='+urllib.parse.quote(name,safe=''),body)['Id']
  actual=api(newpid,'GET','/containers/'+identity+'/json')
  expected=copy.deepcopy(c['Config']);expected['Image']=snapshot['image']
  assert actual['Config']==expected and actual['HostConfig']==expected_host,'Source test service configuration changed'
  created[name]=identity
 api(newpid,'POST','/containers/gitea/start')
 assert not api(newpid,'GET','/containers/jenkins-parity/json')['State']['Running']
 archive=owner/'worker-transport-candidate-20261014.tar'
 with archive.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==QUALIFICATION_ARCHIVE_SHA
 context=engine/'leroy-storage-qualification-20261015';context.mkdir(mode=0o755)
 with tarfile.open(archive) as bundle:
  members=bundle.getmembers();assert len(members)==len(EXPECTED_INPUTS) and {m.name for m in members}==set(EXPECTED_INPUTS)
  for m in members:
   assert m.isfile() and m.name==pathlib.PurePosixPath(m.name).name and m.size<=24*1024**2
   data=bundle.extractfile(m).read();assert sha(data)==EXPECTED_INPUTS[m.name]
   p=context/m.name;p.write_bytes(data);p.chmod(0o644)
 results=context/'results';results.mkdir(mode=0o750);os.chown(results,10001,10001)
 inside='/var/lib/docker/'+context.name
 args=prefix+['run','--rm','--init','--user','10001:10001','--network','none','--read-only','--cap-drop','ALL',
 '--security-opt','no-new-privileges:true','--memory','256m','--memory-swap','256m','--cpus','1','--pids-limit','128',
 '--tmpfs','/tmp:rw,nosuid,size=64m,mode=1777','--mount','type=bind,src='+inside+',dst=/operator,readonly',
 '--mount','type=bind,src='+inside+'/results,dst=/results','-e','PYTHONPATH=/operator/pytest-runtime.zip',
 '-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTEST_DISABLE_PLUGIN_AUTOLOAD=1','-e','LEROY_LEASE_TRACE=1',
 '--name','leroy-storage-qualification-20261015','--label','io.leroy.operator-test=ssd-storage-20261015',
 '--entrypoint','python',WORKER,'-m','pytest','/operator/test_heartbeat.py','/operator/test_lease_transport_trace.py',
 '-k','not docker_operations','-q','-p','no:cacheprovider','--junitxml=/results/storage.xml']
 test=subprocess.run(args,capture_output=True,timeout=180)
 (work/'worker-tests.log').write_bytes(test.stdout+b'\n'+test.stderr);(work/'worker-tests.log').chmod(0o600)
 cases=ET.parse(results/'storage.xml').findall('.//testcase')
 assert test.returncode==0 and len(cases)==28 and all(not any(c.find(k) is not None for k in ('failure','error','skipped')) for c in cases)
 for name in ('controller','postgres'):
  c=inspect('leroy-nas-parity-'+name+'-1');assert (c['Id'],c['Image'],c['State']['Pid'])==(services[name]['Id'],services[name]['Image'],services[name]['State']['Pid'])
 assert sha((owner/'config/runner.toml').read_bytes())==profile_sha
 assert inspect('jenkins')['Id']==native['Id'] and inspect('jenkins')['State']['Pid']==native['State']['Pid']
 checkpoint()
 call(['docker','start',services['runner']['Id']],timeout=40);runner_stopped=False
 result={'engine_root':str(engine),'persistent_volume_source':str(old_root/'volumes'),
  'old_engine_root_retained':True,'old_inactive_test_containers_retained_in_old_pool':True,
  'worker_image':WORKER,'qualified_worker_image_config_and_layers_unchanged':True,'linux_worker_tests':28,
  'source_service_rootfs_snapshots':{n:{k:v for k,v in s.items() if k!='config'} for n,s in snapshots.items()},
  'source_service_configuration_unchanged_except_snapshot_image_reference':True,
  'normalized_docker_defaults':['HostConfig.OomKillDisable null becomes false; OOM killer remains enabled'],
  'existing_named_volumes_reused':True,'gitea_container_id':created['gitea'],'private_jenkins_container_id':created['jenkins-parity'],
  'old_named_engine_volume_reference_retained':True,
  'selected_images_archive_sha256':transfer_sha,'selected_images_archive_bytes':transfer.stat().st_size,
  'only_compose_docker_storage_mounts_changed':True,'controller_and_postgres_restarted':False,
  'production_modified':False,'graphato_sources_or_tests_changed':False,'ssd_free_bytes':shutil.disk_usage(work).free}
 state['phase']='verified';save('state.json',state);save('deployment-proof.json',result)
 # Keep the bounded transfer as additional recovery evidence for now.
except Exception as error:
 state['phase']='failed:'+type(error).__name__;save('state.json',state)
 try:
  if switched:
   c=inspect('leroy-nas-parity-docker-1')
   if c['State']['Running']:call(['docker','stop','--time','90',c['Id']],timeout=120)
   atomic(cfg,before);call(compose+['up','-d','--no-deps','--no-build','--pull','never','docker'],timeout=120)
  else:
   c=inspect('leroy-nas-parity-docker-1')
   if not c['State']['Running']:call(['docker','start',c['Id']],timeout=40)
  restored=inspect('leroy-nas-parity-docker-1')
  for _ in range(60):
   try:
    restored=inspect('leroy-nas-parity-docker-1')
    restored_gitea=api(restored['State']['Pid'],'GET','/containers/gitea/json')
    if not restored_gitea['State']['Running']:api(restored['State']['Pid'],'POST','/containers/gitea/start')
    break
   except (OSError,AssertionError,http.client.HTTPException):time.sleep(1)
  else:raise RuntimeError('Retain failed rollback; owned source service needs inspection')
  if not inspect(services['runner']['Id'])['State']['Running']:call(['docker','start',services['runner']['Id']],timeout=40)
  state['rollback_restored_old_engine']=True;save('state.json',state)
 except Exception as rollback:save('rollback-error.json',{'error_type':type(rollback).__name__})
 raise
print(json.dumps(result))
'''


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--attempt', choices=('a', 'b'), default='a')
    parser.add_argument('--resume-export', action='store_true')
    parser.add_argument('--resume-sequence', choices=(1, 2, 3, 4, 5, 6), type=int, default=1)
    args = parser.parse_args()
    assert args.apply
    suffix = '' if args.attempt == 'a' else '-' + args.attempt
    folder = BASE / ('engine-storage-20261015' + suffix)
    if args.attempt == 'b':
        retained = json.loads(vm.remote("import pathlib\nprint(pathlib.Path('/overlay/leroy-nas-parity-engine-test/20261015/state.json').read_text())", sudo=True))
        assert retained['phase'] == 'failed:InvalidURL' and retained['rollback_restored_old_engine']
    closed = json.loads((ROOT / 'test-results/nas-parity/followup/resource-window-original-night-20261014-c/window-result.json').read_text())
    assert closed['all_seven_original_services_restored_healthy'] and closed['healthy_before_deadline']
    assert folder.exists() == args.resume_export, 'Inspect the retained storage journal; never repeat an uncertain initialization'
    if not args.resume_export:
        folder.mkdir()
    idle()
    guard = begin(folder, 'ssd-engine-initialization')
    before = json.loads((folder / guard).read_text())
    candidate = ROOT / 'test-results/nas-parity/followup/worker-transport-candidate-20261014'
    inputs = json.loads((candidate / 'qualification-start.json').read_text())['inputs_sha256']
    values = {'WORKER': WORKER, 'PRODUCTION': before['jobs'], 'EXPECTED_INPUTS': inputs, 'DAY': '20261015' + suffix,
              'RESUME_EXPORT': args.resume_export,
              'RESUME_SEQUENCE': args.resume_sequence,
              'QUALIFICATION_ARCHIVE_SHA': vm.digest(candidate / 'qualification-inputs.tar')}
    program = ''.join(k + '=' + repr(v) + '\n' for k, v in values.items()) + PROGRAM
    compile(program, 'owned-ssd-engine-initialization', 'exec')
    operation = 'initialization-resume' + str(args.resume_sequence) if args.resume_export else 'initialization'
    (folder / (operation + '-program.py')).write_text(program)
    (folder / (operation + '-started.json')).write_text(json.dumps({'production_guard_before': guard}) + '\n')
    result = json.loads(vm.remote(program, sudo=True, timeout=1800))
    (folder / 'deployment-proof.json').write_text(json.dumps(result, indent=2) + '\n')
    finish(folder, 'ssd-engine-initialization', guard)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
