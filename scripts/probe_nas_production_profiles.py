"""Verify proposed native NAS profile contexts without secrets or application writes."""

import argparse
import hashlib
import json
import tomllib
from datetime import datetime, timezone

from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, run_script

PROBE = r'''
import json,os,pathlib,socket,subprocess,urllib.error,urllib.request
result={'profile':PROFILE,'credentials_supplied':False,'application_writes_performed':False}
result['python_version']=subprocess.check_output(['python3','--version'],text=True).strip()
result['ssh_version']=subprocess.run(['ssh','-V'],capture_output=True,text=True,check=True).stderr.strip()
result['docker_version']=json.loads(subprocess.check_output(['docker','version','--format','{{json .}}']))
# Export versions only, not the daemon's complete operational metadata.
result['docker_version']={side:{k:v for k,v in result['docker_version'][side].items() if k in ['Version','ApiVersion','MinAPIVersion']}
                          for side in ['Client','Server']}
if PROFILE=='gitea':
 status=subprocess.check_output(['docker','inspect','gitea','--format','{{.State.Status}}'],text=True).strip()
 assert status=='running';result['existing_native_gitea_accessible']=True
elif PROFILE=='graphato':
 result['buildx_version']=subprocess.check_output(['docker','buildx','version'],text=True).strip()
 result['compose_version']=subprocess.check_output(['docker','compose','version','--short'],text=True).strip()
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open('http://127.0.0.1:5005/v2/',timeout=10) as response:
  result['nas_loopback_registry_http_status']=response.status
 assert result['nas_loopback_registry_http_status']==200
elif PROFILE=='operations':
 rows=[]
 for name in ('/srv/music','/srv/yt-music'):
  p=pathlib.Path(name);assert p.is_dir() and os.access(p,os.R_OK|os.X_OK)
  with os.scandir(p) as entries:has_entry=next(entries,None) is not None
  readonly=bool(os.statvfs(p).f_flag & os.ST_RDONLY);assert readonly
  rows.append({'destination':name,'directory_readable':True,'nonempty':has_entry,'filesystem_read_only':True})
 result['music_sources']=rows
 with socket.create_connection(('192.168.178.84',8022),timeout=5):pass
 result['smartphone_ssh_tcp_reachable']=True
print(json.dumps(result))
'''

PROGRAM = r'''
import hashlib,json,pathlib,shutil,subprocess,uuid
root=pathlib.Path('/volume1/docker/leroy-nas-parity').resolve(strict=True)
assert (root/'.leroy-owned').is_file()
archive=pathlib.Path(ARCHIVE['path']).resolve(strict=True)
assert archive.is_relative_to(root/'release-images') and archive.stat().st_size==ARCHIVE['bytes']
with archive.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==ARCHIVE['sha256']
if ATTEMPT==3:
 assert set(IDENTITIES)==set(ARCHIVE['image_ids'])
 assert all(row['source_oci_index_digest']==index and row['platform']=='linux/amd64'
            and row['image_configuration_blob_hash_matches_native_id']
            and row['native_rootfs_layers_match_archived_configuration'] for index,row in IDENTITIES.items())
 expected={row['native_classic_image_id'] for row in IDENTITIES.values()}
else:expected=set(ARCHIVE['image_ids'])
assert expected=={p['image'] for p in PROFILES.values()}
docker_root=subprocess.check_output(['docker','info','--format','{{.DockerRootDir}}'],text=True).strip()
assert shutil.disk_usage(docker_root).free>=3*1024**3
tags={'leroy-job:nas-parity':'sha256:0f1ac53379ffb5351a4bd9c0fb8d93d7c41ca06fcb8be35e887e93c92370d6bc',
      'leroy-job:nas-parity-gitea':'sha256:bdce891ed50d1156316e9ca9a882e07e14f9a17045cccc521fd3d69146cdbf80'}
previous_tags={}
for tag,image in tags.items():
 r=subprocess.run(['docker','image','inspect',tag,'--format','{{.Id}}'],capture_output=True,text=True,timeout=20)
 previous_tags[tag]=None if r.returncode else r.stdout.strip()
 if ATTEMPT==1:assert r.returncode or r.stdout.strip()==image,'Do not replace a different existing native image tag'
missing=[i for i in expected if subprocess.run(['docker','image','inspect',i],capture_output=True,timeout=20).returncode]
if ATTEMPT==3:assert not missing,'Use the verified existing native configuration IDs; do not import or retag source aliases'
if missing:
 print(json.dumps({'phase':'loading_verified_owned_job_images','archive_sha256':ARCHIVE['sha256']}),flush=True)
 # Keep every prior native alias recoverable. The archive only names our two
 # job tags; restore their original mappings after importing immutable IDs.
 if ATTEMPT>1:
  for tag,image in previous_tags.items():
   if image:subprocess.run(['docker','tag',image,'leroy-retained:job-'+image.removeprefix('sha256:')[:12]],check=True,capture_output=True)
 try:
  r=subprocess.run(['docker','load','-i',str(archive)],capture_output=True,text=True,timeout=600)
  assert r.returncode==0,'Retain failed image import for diagnosis'
  for image in expected:
   subprocess.run(['docker','tag',image,'leroy-verified-job:'+image.removeprefix('sha256:')[:12]],check=True,capture_output=True)
 finally:
  if ATTEMPT>1:
   for tag,image in previous_tags.items():
    if image:subprocess.run(['docker','tag',image,tag],check=True,capture_output=True)
    else:subprocess.run(['docker','image','rm',tag],capture_output=True)
 for tag,image in previous_tags.items():
  r=subprocess.run(['docker','image','inspect',tag,'--format','{{.Id}}'],capture_output=True,text=True)
  if image:assert r.returncode==0 and r.stdout.strip()==image
  else:assert r.returncode
for image in expected:
 v=json.loads(subprocess.check_output(['docker','image','inspect',image]))[0]
 assert v['Id']==image and v['Os']=='linux' and v['Architecture']=='amd64'
 assert v['RootFS']['Layers']==LAYERS[image]
 if ATTEMPT==3:
  tag='leroy-verified-job:'+image.removeprefix('sha256:')[:12]
  prior=subprocess.run(['docker','image','inspect',tag,'--format','{{.Id}}'],capture_output=True,text=True)
  assert prior.returncode or prior.stdout.strip()==image,'Retain any different existing verified alias'
  if prior.returncode:subprocess.run(['docker','tag',image,tag],check=True,capture_output=True)
rows={}
for profile,settings in PROFILES.items():
 name='leroy-production-profile-probe-'+profile+'-'+uuid.uuid4().hex[:8]
 mounts=[]
 for value in settings['mounts']:
  # Use the existing verified tool files for this isolated preflight only;
  # the eventual deployment still needs its separate production tools bundle.
  value=value.replace('/volume1/docker/leroy-production/tools/docker',str(root/'fixtures/graphato-tools/bin/docker'))
  value=value.replace('/volume1/docker/leroy-production/tools/cli-plugins',str(root/'fixtures/graphato-tools/docker-config/cli-plugins'))
  mounts+=['--mount',value]
 args=['docker','create','--name',name,'--label','io.leroy.production-review=profiles','--read-only',
       '--network',settings['network'],'--memory',settings['memory'],'--cpus',str(settings['cpus']),
       '--pids-limit',str(settings.get('pids_limit',1024)),'--cap-drop','ALL','--security-opt','no-new-privileges',
       '--mount','type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock',*mounts]
 if settings.get('memory_swap'):args+=['--memory-swap',settings['memory_swap']]
 args+=['--entrypoint','python',settings['image'],'-B','-c','PROFILE='+repr(profile)+'\n'+PROBE]
 try:
  subprocess.run(args,check=True,capture_output=True,timeout=30)
  created=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
  assert created['Image']==settings['image']
  assert created['HostConfig']['ReadonlyRootfs'] and created['HostConfig']['NetworkMode']==settings['network']
  r=subprocess.run(['docker','start','-a',name],capture_output=True,text=True,timeout=120)
  if r.returncode:
   rows[profile]={'passed':False,'exit_code':r.returncode,'stdout_sha256':hashlib.sha256(r.stdout.encode()).hexdigest(),
                  'stderr_sha256':hashlib.sha256(r.stderr.encode()).hexdigest(),
                  'exception_types':__import__('re').findall(r'^([A-Za-z]+Error):',r.stderr,__import__('re').MULTILINE)}
  else:
   value=json.loads(r.stdout);value['passed']=True
   value['actual_limits']={k:created['HostConfig'][k] for k in ('Memory','MemorySwap','NanoCpus','PidsLimit')}
   value['network_mode']=created['HostConfig']['NetworkMode']
   value['image_id']=created['Image'];value['mounts']=[{'destination':m['Destination'],'read_only':not m['RW']} for m in created['Mounts']]
   rows[profile]=value
 finally:
  subprocess.run(['docker','rm','-f','-v',name],capture_output=True,timeout=30)
 print(json.dumps({'profile':profile,'passed':rows[profile]['passed']}),flush=True)
for tag,image in previous_tags.items():
 r=subprocess.run(['docker','image','inspect',tag,'--format','{{.Id}}'],capture_output=True,text=True)
 assert (r.returncode==0 and r.stdout.strip()==image) if image else r.returncode
output={'profiles':rows,'passed':all(row['passed'] for row in rows.values()),'native_images_loaded':missing,
        'archive_sha256_verified':True,'image_ids_and_layers_verified':True,
        'previous_native_job_tag_mappings':previous_tags,'previous_native_job_tag_mappings_preserved':True,
        'image_store_identity_mapping':IDENTITIES if ATTEMPT==3 else None,
        'production_configuration_applied':False,'credentials_installed':False,
        'application_business_workloads_executed':False,'test_isolation_modified':False,
        'production_application_modified':False,'production_replacement_ready':False}
print('RESULT='+json.dumps(output),flush=True)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--reason')
    args = parser.parse_args()
    folder = ROOT / 'test-results/nas-parity/followup/cutover-preparation'
    destination = folder / ('native-context-profile-preflight' + (f'-attempt-{args.attempt}' if args.attempt > 1 else '') + '.json')
    assert not destination.exists(), 'Retain the original context preflight; do not implicitly rerun'
    if args.attempt > 1:
        prior = folder / ('native-context-profile-preflight' + (f'-attempt-{args.attempt - 1}' if args.attempt > 2 else '') + '.json')
        assert args.reason and json.loads(prior.read_text())['passed'] is False
    config = tomllib.loads((ROOT / 'infra/nas/production/config/runner.toml').read_text())
    release = json.loads((ROOT / 'test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/release-image-restore.json').read_text())
    images = release['archives']['job-images.tar.gz']
    layers = {image: release['restored_images'][image]['rootfs_layers'] for image in images['image_ids']}
    identities = {}
    if args.attempt == 3:
        identities = json.loads((folder / 'native-job-image-identity-mapping.json').read_text())['images']
        assert all(row['rootfs_layers'] == layers[index] for index, row in identities.items())
        layers = {row['native_classic_image_id']: layers[index] for index, row in identities.items()}
        identities = {index: {key: value for key, value in row.items()
                               if key not in {'rootfs_layers', 'source_repo_tags_already_resolve_native_id'}}
                      for index, row in identities.items()}
    # Keep the SSH command below the Windows CreateProcess argument limit.
    # Secret references and unused environments are not needed by this probe.
    profiles = {name: {key: value for key, value in row.items()
                       if key in {'image', 'network', 'memory', 'memory_swap', 'cpus', 'pids_limit', 'mounts'}}
                for name, row in config['profiles'].items()}
    program = 'ARCHIVE=' + repr(images) + '\nLAYERS=' + repr(layers) + '\nPROFILES=' + repr(profiles)
    program += '\nIDENTITIES=' + repr(identities)
    program += '\nPROBE=' + repr(PROBE) + '\nATTEMPT=' + repr(args.attempt) + '\n' + PROGRAM
    compile(program, 'native production profile read-only preflight', 'exec')
    phase = 'profiles-attempt-' + str(args.attempt)
    production_before = begin(folder, phase)
    result = run_script("python3 - <<'PY'\n" + program + "\nPY\n", ROOT / '.local/nas-ssh.json',
                        sudo=True, timeout=1200)
    qualification = finish(folder, phase, production_before)
    if result.returncode:
        failure = {'passed': False, 'dispatcher_exit_code': result.returncode,
                   'stdout_sha256': hashlib.sha256(result.stdout.encode()).hexdigest(),
                   'stderr_sha256': hashlib.sha256(result.stderr.encode()).hexdigest(),
                   'attempt': args.attempt, 'reason': args.reason,
                   'exception_types': __import__('re').findall(r'^([A-Za-z]+Error):', result.stderr, __import__('re').MULTILINE),
                   'last_traceback_line': __import__('re').findall(r'File "<stdin>", line (\d+)', result.stderr)[-1:],
                   'production_replacement_ready': False}
        destination.write_text(json.dumps(failure, indent=2) + '\n')
        raise RuntimeError('Native preflight failed; retained sanitized failure, no production workload started')
    lines = result.stdout.splitlines()
    value = json.loads(next(line.removeprefix('RESULT=') for line in lines if line.startswith('RESULT=')))
    value['at'] = datetime.now(timezone.utc).isoformat()
    value['attempt'] = args.attempt
    value['reason'] = args.reason
    value['production_measurement_qualification'] = qualification
    value['scope'] = 'Native profile execution, Docker/tool versions and read-only source access; no credentials or application acceptance'
    destination.write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({'profiles': {k: v['passed'] for k, v in value['profiles'].items()},
                      'passed': value['passed'], 'production_replacement_ready': False}), flush=True)


if __name__ == '__main__':
    main()
