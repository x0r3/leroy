"""Archive tested image IDs and restore them to an empty, disconnected test daemon."""

import argparse
import json
import re
from datetime import datetime, timezone

from nas_gitea_target import idle
from nas_ssh import ROOT, run_script

PROGRAM = r'''
import gzip,hashlib,json,pathlib,shutil,subprocess,threading,time,uuid
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
folder=root/'release-images'/COMMIT
assert not folder.parent.is_symlink() and folder.resolve().is_relative_to(root.resolve())
if ATTEMPT:
 assert folder.is_dir() and (folder/'started.json').is_file() and not (folder/'result.json').exists()
 attempt=folder/'attempts'/ATTEMPT
 assert not attempt.exists(),'Preserve every explicit restore attempt'
 attempt.mkdir(parents=True,mode=0o700)
else:
 assert not folder.exists(),'Inspect the retained archive attempt before repeating it'
 folder.mkdir(parents=True,mode=0o700);attempt=folder
assert not folder.is_symlink() and not attempt.is_symlink() and attempt.resolve().is_relative_to(root.resolve())
(attempt/'started.json').write_text(json.dumps({'commit':COMMIT,'scope':'owned test-stack images only','retained_archives_reused':bool(ATTEMPT)})+'\n')
inner=['docker','exec','leroy-nas-parity-docker-1','docker']
def command(*args,timeout=120):
 return subprocess.check_output(list(args),stderr=subprocess.PIPE,timeout=timeout)
def watchdog(process):
 timer=threading.Timer(600,process.terminate);timer.daemon=True;timer.start();return timer
host_ids=sorted(set(PINS['service_images'].values()));job_ids=sorted(set(PINS['job_images'].values()))
cases=[('host-images.tar.gz',['docker'],host_ids),('job-images.tar.gz',inner,job_ids)]
expected={};image_sizes={};sources={}
for name,identity in PINS['service_images'].items():
 info=json.loads(command('docker','inspect','leroy-nas-parity-'+name+'-1'))[0]
 assert info['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
 assert info['Image']==identity and info['State']['Running']
for filename,prefix,identities in cases:
 info=json.loads(command(*prefix,'info','--format','{{json .}}'))
 sources[filename]={'containerd_image_store':dict(info.get('DriverStatus',[])).get('driver-type')=='io.containerd.snapshotter.v1','driver':info['Driver'],'server_version':info['ServerVersion']}
 for row in json.loads(command(*prefix,'image','inspect',*identities)):
  assert row['Id'] in identities;expected[row['Id']]={'rootfs_layers':row['RootFS']['Layers']};image_sizes[row['Id']]=row['Size']
for name,row in BEFORE['job_profiles'].items():
 assert PINS['job_images'][name]==row['image_id'] and expected[row['image_id']]['rootfs_layers']==row['rootfs_layers']
assert not command(*inner,'ps','-a','--filter','label=io.leroy.runner=runner-nas-parity','-q').strip()
docker_root=pathlib.Path(command('docker','info','--format','{{.DockerRootDir}}').decode().strip())
required=3*sum(image_sizes.values())+1024**3
disk_preflight={'required_free_bytes':required,'archive_filesystem_free_bytes':shutil.disk_usage(root).free,'restore_filesystem_free_bytes':shutil.disk_usage(docker_root).free}
assert min(disk_preflight['archive_filesystem_free_bytes'],disk_preflight['restore_filesystem_free_bytes'])>=required
(attempt/'disk-preflight.json').write_text(json.dumps(disk_preflight)+'\n')
archives={}
for filename,prefix,identities in cases:
 path=folder/filename
 if ATTEMPT:assert path.is_file() and path.stat().st_size>0
 else:
  with (folder/(filename+'.stderr')).open('wb') as errors:
   process=subprocess.Popen([*prefix,'image','save',*identities],stdout=subprocess.PIPE,stderr=errors);timer=watchdog(process)
   try:
    with gzip.open(path,'wb',compresslevel=1) as output:
     while chunk:=process.stdout.read(1024**2):output.write(chunk)
    assert process.wait(timeout=600)==0,'Bounded image export failed'
   finally:
    timer.cancel();process.stdout.close()
    if process.poll() is None:process.terminate();process.wait(timeout=30)
 with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
 archives[filename]={'path':str(path),'bytes':path.stat().st_size,'sha256':digest,'image_ids':identities}
(attempt/'archives.json').write_text(json.dumps(archives,indent=2)+'\n')
restored={};daemons=[]
for filename,source_prefix,identities in cases:
 token=uuid.uuid4().hex;name='leroy-image-restore-'+token;label='io.leroy.image-restore='+token;volume=name+'-data'
 containerd=sources[filename]['containerd_image_store'];config={'features':{'containerd-snapshotter':containerd}}
 if not containerd:config['storage-driver']='overlay2'
 config_path=attempt/(filename+'.daemon.json');config_path.write_text(json.dumps(config)+'\n');config_path.chmod(0o600)
 daemon_id=None;volume_created=False
 try:
  command('docker','volume','create','--label',label,volume);volume_created=True
  daemon_id=command('docker','run','-d','--name',name,'--label',label,'--privileged','--network','none',
   '--memory','768m','--memory-swap','768m','--cpus','1','-e','DOCKER_TLS_CERTDIR=',
   '-v',volume+':/var/lib/docker','-v',str(config_path)+':/restore/daemon.json:ro','--entrypoint','dockerd-entrypoint.sh',
   PINS['service_images']['docker'],'dockerd','--config-file=/restore/daemon.json','--host=unix:///var/run/docker.sock','--iptables=false','--bridge=none').decode().strip()
  assert len(daemon_id)==64
  info=json.loads(command('docker','inspect',daemon_id))[0]
  assert info['Config']['Labels']['io.leroy.image-restore']==token and info['HostConfig']['NetworkMode']=='none' and not info['HostConfig']['PortBindings']
  assert info['HostConfig']['Memory']==info['HostConfig']['MemorySwap']==768*1024**2
  prefix=['docker','exec',daemon_id,'docker'];deadline=time.monotonic()+90
  while time.monotonic()<deadline:
   try:command(*prefix,'info',timeout=10);break
   except (subprocess.CalledProcessError,subprocess.TimeoutExpired):time.sleep(2)
  else:raise TimeoutError('Disconnected restore daemon did not become ready')
  store=json.loads(command(*prefix,'info','--format','{{json .}}'))
  assert (dict(store.get('DriverStatus',[])).get('driver-type')=='io.containerd.snapshotter.v1')==containerd
  assert not command(*prefix,'image','ls','--format','json').strip()
  path=folder/filename
  with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==archives[filename]['sha256']
  with (attempt/(filename+'.load.stdout')).open('wb') as output,(attempt/(filename+'.load.stderr')).open('wb') as errors,gzip.open(path,'rb') as stream:
   process=subprocess.Popen(['docker','exec','-i',daemon_id,'docker','image','load'],stdin=subprocess.PIPE,stdout=output,stderr=errors);timer=watchdog(process)
   try:
    while chunk:=stream.read(1024**2):process.stdin.write(chunk)
    process.stdin.close();assert process.wait(timeout=600)==0,'Bounded image load failed'
   finally:
    timer.cancel()
    if not process.stdin.closed:process.stdin.close()
    if process.poll() is None:process.terminate();process.wait(timeout=30)
  imported={row['Id']:{'rootfs_layers':row['RootFS']['Layers']} for row in json.loads(command(*prefix,'image','inspect',*identities))}
  assert imported=={key:expected[key] for key in identities};restored.update(imported)
  assert not command(*prefix,'ps','-aq').strip(),'No workloads may start in the restore daemon'
  info=json.loads(command('docker','inspect',daemon_id))[0];assert not info['State']['OOMKilled'] and info['RestartCount']==0
  daemons.append({'archive':filename,'source_storage':sources[filename],'restored_storage_driver':store['Driver'],'empty_before_restore':True,'image_ids_and_layers_match':True,'workloads_started':False})
 except Exception as error:
  (attempt/'failure.json').write_text(json.dumps({'passed':False,'archive':filename,'exception_type':type(error).__name__,'exit_code':getattr(error,'returncode',None)})+'\n');raise
 finally:
  if daemon_id is not None:
   info=json.loads(command('docker','inspect',daemon_id))[0];assert info['Config']['Labels']['io.leroy.image-restore']==token and info['Name']=='/'+name
   logs=subprocess.run(['docker','logs',daemon_id],capture_output=True,timeout=30);logs.check_returncode()
   (attempt/(filename+'.daemon.log')).write_bytes(logs.stdout+logs.stderr)
   command('docker','rm','-f',daemon_id)
  if volume_created:
   info=json.loads(command('docker','volume','inspect',volume))[0];assert info['Labels']['io.leroy.image-restore']==token and info['Name']==volume
   command('docker','volume','rm',volume)
assert restored==expected
result={'passed':True,'commit':COMMIT,'archives':archives,'restored_images':restored,'restored_image_count':len(restored),
 'empty_daemon_before_restore':True,'image_ids_and_layers_match':True,'disk_preflight':disk_preflight,
 'restore_network_mode':'none','restore_ports_published':False,'workloads_started':False,
 'source_storage_matched_per_archive':True,'restore_daemons':daemons,'retained_archives_reused':bool(ATTEMPT),'attempt':ATTEMPT,
 'temporary_restore_resources_removed':True,'production_modified':False,'secret_values_exported':False,
 'scope':'Tested service and job images restored to separate matching storage models; not application data or the complete nested Docker engine'}
(attempt/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if attempt!=folder:(folder/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))

'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--attempt", choices=["storage-matched", "storage-matched-wait"], help="Reuse retained archives after diagnosing the earlier restore failure")
    args = parser.parse_args()
    assert re.fullmatch(r"[a-f0-9]{40}", args.commit)
    folder = ROOT / "test-results/nas-parity/followup/candidates/graphato" / args.commit
    destination = folder / "release-image-restore.json"
    assert not destination.exists(), "Retain previous image restore attempts"
    pins = json.loads((folder / "release-image-pins.json").read_text())
    before = json.loads((folder / "nas-release-configuration-before.json").read_text())
    assert pins["tested_image_layers_unchanged"] and not pins["production_modified"]
    if args.attempt:
        failure = json.loads((folder / "release-image-restore-first-failure.json").read_text())
        source = json.loads((folder / "release-image-source-storage.json").read_text())
        assert not failure["passed"] and failure["archives_retained"]
        assert dict(source["daemon"]["DriverStatus"])["driver-type"] == "io.containerd.snapshotter.v1"
        if args.attempt == "storage-matched-wait":
            prior = json.loads((folder / "release-image-restore-wait-failure.json").read_text())
            assert prior["failure"]["exception_type"] == "TimeoutExpired"
            assert not prior["remaining_restore_containers"] and not prior["remaining_restore_volumes"]
    idle()
    values = "COMMIT=" + repr(args.commit) + "\nATTEMPT=" + repr(args.attempt) + "\nPINS=" + repr(pins) + "\nBEFORE=" + repr(before) + "\n"
    result = run_script("python3 - <<'PY'\n" + values + PROGRAM + "\nPY\n", ROOT / ".local/nas-ssh.json", timeout=1800)
    assert result.returncode == 0, result.stderr[-1500:]
    record = json.loads(result.stdout)
    record.update(at=datetime.now(timezone.utc).isoformat())
    destination.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"passed": record["passed"], "restored_image_count": record["restored_image_count"],
                      "network_mode": "none", "temporary_restore_resources_removed": True}), flush=True)


if __name__ == "__main__":
    main()
