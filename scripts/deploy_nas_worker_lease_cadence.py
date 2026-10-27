"""Install the exact Linux-qualified cadence worker in the idle NAS test profile."""

import argparse
import json

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from qualify_nas_worker_lease_cadence import FOLDER, OLD_IMAGE, require_restored_windows

PROGRAM = r'''
import hashlib,json,os,pathlib,re,subprocess,tomllib
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
def call(args,timeout=30):
 r=subprocess.run(args,capture_output=True,timeout=timeout)
 assert r.returncode==0,'Scoped worker installation failed; output withheld'
 return r.stdout
def inspect(name):return json.loads(call(['docker','inspect',name]))[0]
def sha(data):return hashlib.sha256(data).hexdigest()
def save(path,value):
 temporary=path.with_suffix(path.suffix+'.pending');assert not temporary.exists()
 with temporary.open('x') as stream:
  os.chmod(temporary,0o600);json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
 temporary.replace(path);fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
outer=inspect('leroy-nas-parity-docker-1');assert outer['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
prefix=['docker','exec',outer['Id'],'docker']
assert call(prefix+['inspect','jenkins-parity','--format','{{.State.Running}}']).decode().strip()=='false'
assert not call(prefix+['ps','-aq','--filter','label=io.leroy.runner=runner-nas-parity']).strip()
for item in json.loads(call(['docker','inspect','paperless','sonarr','radarr','sabnzbd','plex','yt-downloader-service','mail-ingest-service'])):
 assert item['State']['Running'] and item['State'].get('Health',{}).get('Status') in (None,'healthy')
qualified=json.loads((root/'worker-lease-cadence-qualification-20261014/validation.json').read_text())
assert qualified['all_passed'] and qualified['candidate_image']==CANDIDATE and qualified['worker_sha256']==NEW_SHA
assert qualified['old_counterexamples']==5 and qualified['linux_heartbeat_tests']==22 and qualified['linux_runner_tests']==1 and qualified['skipped']==0
assert qualified['runner_image']==inspect('leroy-nas-parity-runner-1')['Image']
old=json.loads(call(prefix+['image','inspect',OLD_IMAGE]))[0];new=json.loads(call(prefix+['image','inspect',CANDIDATE]))[0]
assert old['Config']==new['Config'] and old['RootFS']['Layers']==new['RootFS']['Layers'][:-1]
code="import pathlib,hashlib,leroy.worker;print(hashlib.sha256(pathlib.Path(leroy.worker.__file__).read_bytes()).hexdigest())"
actual=call(prefix+['run','--rm','--network','none','--memory','128m','--memory-swap','128m','--cpus','0.5','--entrypoint','python',CANDIDATE,'-c',code],timeout=60).decode().strip()
assert actual==NEW_SHA
work=root/'worker-lease-cadence-deployment-20261014';path=root/'config/runner.toml'
if not RESUME:
 assert not work.exists();work.mkdir(mode=0o700)
 before=path.read_bytes();config=tomllib.loads(before.decode());assert config['profiles']['graphato']['image']==OLD_IMAGE
 text=before.decode();start=text.index('[profiles.graphato]');end=text.find('\n[',start+len('[profiles.graphato]'));end=len(text) if end<0 else end
 block=text[start:end];assert block.count(OLD_IMAGE)==1
 after=(text[:start]+block.replace(OLD_IMAGE,CANDIDATE)+text[end:]).encode()
 expected=tomllib.loads(after.decode());expected['profiles']['graphato']['image']=OLD_IMAGE;assert expected==config
 for name,data in [('runner-before.toml',before),('runner-after.toml',after)]:
  with (work/name).open('xb') as stream:os.chmod(work/name,0o600);stream.write(data);stream.flush();os.fsync(stream.fileno())
 runner=inspect('leroy-nas-parity-runner-1')
 state={'phase':'prepared','candidate':CANDIDATE,'worker_sha256':NEW_SHA,'old_config_sha256':sha(before),'new_config_sha256':sha(after),
  'runner_id':runner['Id'],'runner_image':runner['Image'],'runner_pid':runner['State']['Pid'],'runner_started_at':runner['State']['StartedAt'],
  'runner_configuration_sha256':sha(json.dumps({k:runner[k] for k in ('Config','HostConfig')},sort_keys=True).encode()),
  'other_services':{name:{'id':c['Id'],'image':c['Image'],'pid':c['State']['Pid']} for name in ('controller','postgres','docker') for c in [inspect('leroy-nas-parity-'+name+'-1')]}}
 save(work/'state.json',state)
else:
 assert work.is_dir();state=json.loads((work/'state.json').read_text());assert state['candidate']==CANDIDATE and state['worker_sha256']==NEW_SHA
 before=(work/'runner-before.toml').read_bytes();after=(work/'runner-after.toml').read_bytes()
 assert sha(before)==state['old_config_sha256'] and sha(after)==state['new_config_sha256']
assert sha(path.read_bytes()) in {state['old_config_sha256'],state['new_config_sha256']},'Profile changed outside this reviewed installation'
if sha(path.read_bytes())==state['old_config_sha256']:
 stat=path.stat();temporary=path.with_suffix('.lease-cadence.tmp');assert not temporary.exists()
 with temporary.open('xb') as stream:
  os.chmod(temporary,stat.st_mode&0o777);os.chown(temporary,stat.st_uid,stat.st_gid);stream.write(after);stream.flush();os.fsync(stream.fileno())
 assert path.read_bytes()==before;temporary.replace(path);fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
state['phase']='profile_updated';save(work/'state.json',state)
runner=inspect('leroy-nas-parity-runner-1');assert runner['Id']==state['runner_id'] and runner['Image']==state['runner_image']
if (runner['State']['Pid'],runner['State']['StartedAt'])==(state['runner_pid'],state['runner_started_at']):
 call(['docker','restart','--time','30',runner['Id']],timeout=60)
current=inspect('leroy-nas-parity-runner-1')
assert current['State']['Running'] and not current['State']['OOMKilled']
assert (current['State']['Pid'],current['State']['StartedAt'])!=(state['runner_pid'],state['runner_started_at'])
assert sha(json.dumps({k:current[k] for k in ('Config','HostConfig')},sort_keys=True).encode())==state['runner_configuration_sha256']
mount=next(m for m in current['Mounts'] if m['Source']==str(path))
assert sha(call(['docker','exec',current['Id'],'cat',mount['Destination']]))==state['new_config_sha256']
for name,prior in state['other_services'].items():
 info=inspect('leroy-nas-parity-'+name+'-1');assert info['Id']==prior['id'] and info['Image']==prior['image'] and info['State']['Pid']==prior['pid']
state['phase']='verified';save(work/'state.json',state)
result={'previous_worker_image':OLD_IMAGE,'worker_image':CANDIDATE,'worker_sha256':NEW_SHA,
 'exact_linux_qualified_image_deployed':True,'changed_profile_fields':['graphato.image'],
 'image_configuration_unchanged':True,'base_layers_retained':True,'renewal_cadence_changed':True,
 'local_cutoff_seconds':45,'server_lease_seconds':90,'lease_deadlines_changed':False,
 'runner_restarted':True,'controller_postgres_and_daemon_restarted':False,
 'graphato_source_or_tests_changed':False,'production_modified':False}
save(work/'deployment-proof.json',result);print(json.dumps(result))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resume-prepared', action='store_true')
    args = parser.parse_args()
    assert args.apply
    require_restored_windows()
    proof = json.loads((FOLDER / 'qualification-proof.json').read_text())['validation']
    assert proof['all_passed'] and proof['old_counterexamples'] == 5 and proof['linux_heartbeat_tests'] == 22
    assert proof['linux_runner_tests'] == 1 and proof['runner_test_passed']
    assert vm.digest(vm.ROOT / 'src/leroy/worker.py') == proof['worker_sha256']
    assert not (FOLDER / 'deployment-proof.json').exists(), 'Retain the completed installation'
    marker = FOLDER / 'deployment-start.json'
    assert marker.exists() == args.resume_prepared, 'Inspect an uncertain installation before explicitly resuming'
    idle()
    assert not vm.state()['State']['Running']
    if marker.exists():
        guard = json.loads(marker.read_text())['production_guard_before']
    else:
        guard = begin(FOLDER, 'worker-cadence-deployment')
        marker.write_text(json.dumps({'production_guard_before': guard, 'candidate': proof['candidate_image']}) + '\n')
    program = ('OLD_IMAGE=' + repr(OLD_IMAGE) + '\nCANDIDATE=' + repr(proof['candidate_image']) +
               '\nNEW_SHA=' + repr(proof['worker_sha256']) + '\nRESUME=' + repr(args.resume_prepared) + '\n' + PROGRAM)
    (FOLDER / 'deployment-program.py').write_text(program)
    value = json.loads(vm.remote(program, sudo=True, timeout=300))
    (FOLDER / 'deployment-proof.json').write_text(json.dumps(value, indent=2) + '\n')
    finish(FOLDER, 'worker-cadence-deployment', guard)
    print(json.dumps(value))


if __name__ == '__main__':
    main()
