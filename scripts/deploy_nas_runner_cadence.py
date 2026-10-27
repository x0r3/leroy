"""Deploy only the Linux-qualified startup cadence layer to the idle test Runner."""

import json

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from qualify_nas_runner_cadence import FOLDER, OLD_IMAGE

PROGRAM = r'''
import copy,hashlib,json,os,pathlib,subprocess,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
def call(args,timeout=30,**kw):
 r=subprocess.run(args,capture_output=True,timeout=timeout,**kw)
 assert r.returncode==0,'Owned Runner deployment failed; output withheld'
 return r.stdout
def inspect(name):return json.loads(call(['docker','inspect',name]))[0]
def sha(data):return hashlib.sha256(data).hexdigest()
def save(path,value):
 p=path.with_suffix(path.suffix+'.pending');assert not p.exists()
 with p.open('x') as f:
  os.chmod(p,0o600);json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 p.replace(path)
 fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
services={n:inspect('leroy-nas-parity-'+n+'-1') for n in ('controller','postgres','runner','docker')}
assert all(c['State']['Running'] and c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' for c in services.values())
prefix=['docker','exec',services['docker']['Id'],'docker']
assert call(prefix+['inspect','jenkins-parity','--format','{{.State.Running}}']).strip()==b'false'
assert not call(prefix+['ps','-aq','--filter','label=io.leroy.runner=runner-nas-parity']).strip()
for c in json.loads(call(['docker','inspect','paperless','sonarr','radarr','sabnzbd','plex','yt-downloader-service','mail-ingest-service'])):
 assert c['State']['Running'] and c['State'].get('Health',{}).get('Status') in (None,'healthy')
qualified=json.loads((root/'runner-cadence-qualification-20261015/validation.json').read_text())
assert qualified['all_passed'] and qualified['linux_runner_tests']==23 and qualified['old_counterexamples']==5
assert qualified['candidate_image']==CANDIDATE and qualified['worker_sha256']==SOURCE_SHA
old=json.loads(call(['docker','image','inspect',OLD_IMAGE]))[0];new=json.loads(call(['docker','image','inspect',CANDIDATE]))[0]
assert old['Config']==new['Config'] and new['RootFS']['Layers'][:-1]==old['RootFS']['Layers']
compose=['docker','compose','--project-directory',str(root),'-p','leroy-nas-parity','-f',str(root/'compose.yaml'),'-f',str(root/'compose.override.yaml')]
path=root/'compose.override.yaml';work=root/'runner-cadence-deployment-20261015'
if not RESUME:
 assert not work.exists();work.mkdir(mode=0o700)
 assert services['runner']['Image']==OLD_IMAGE
 before=path.read_bytes();config=json.loads(before);assert 'image' not in config['services']['runner']
 after=copy.deepcopy(config);after['services']['runner']['image']=CANDIDATE
 after=(json.dumps(after,indent=2)+'\n').encode()
 for name,data in [('override-before.json',before),('override-after.json',after)]:
  p=work/name;p.write_bytes(data);p.chmod(0o600)
 canonical=json.loads(call(compose+['config','--format','json']))
 assert json.loads(call(['docker','image','inspect',canonical['services']['runner']['image']]))[0]['Id']==OLD_IMAGE
 canonical['services']['runner']['image']=CANDIDATE
 state={'phase':'prepared','old_sha':sha(before),'new_sha':sha(after),'candidate':CANDIDATE,
  'expected_compose_sha':sha(json.dumps(canonical,sort_keys=True).encode()),
  'old_runner_id':services['runner']['Id'],'runner_profile_sha':sha((root/'config/runner.toml').read_bytes()),
  'others':{n:{'id':c['Id'],'pid':c['State']['Pid'],'image':c['Image']} for n,c in services.items() if n!='runner'}}
 save(work/'state.json',state)
else:
 state=json.loads((work/'state.json').read_text());assert state['candidate']==CANDIDATE
 before=(work/'override-before.json').read_bytes();after=(work/'override-after.json').read_bytes()
 assert sha(before)==state['old_sha'] and sha(after)==state['new_sha']
assert path.read_bytes() in (before,after)
if path.read_bytes()==before:
 st=path.stat();p=path.with_suffix('.cadence.pending');assert not p.exists()
 with p.open('xb') as f:
  os.chmod(p,st.st_mode&0o777);os.chown(p,st.st_uid,st.st_gid);f.write(after);f.flush();os.fsync(f.fileno())
 assert path.read_bytes()==before;p.replace(path)
 fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
actual=json.loads(call(compose+['config','--format','json']))
assert sha(json.dumps(actual,sort_keys=True).encode())==state['expected_compose_sha']
state['phase']='override_updated';save(work/'state.json',state)
runner=inspect('leroy-nas-parity-runner-1')
if runner['Image']!=CANDIDATE:
 assert runner['Id']==state['old_runner_id'] and runner['Image']==OLD_IMAGE
 call(compose+['up','-d','--no-deps','--no-build','--pull','never','runner'],timeout=120)
runner=inspect('leroy-nas-parity-runner-1')
assert runner['State']['Running'] and not runner['State']['OOMKilled'] and runner['Image']==CANDIDATE
assert sha((root/'config/runner.toml').read_bytes())==state['runner_profile_sha']
code="import hashlib,pathlib,leroy.worker;print(hashlib.sha256(pathlib.Path(leroy.worker.__file__).read_bytes()).hexdigest())"
assert call(['docker','exec',runner['Id'],'python','-c',code]).decode().strip()==SOURCE_SHA
for n,b in state['others'].items():
 c=inspect('leroy-nas-parity-'+n+'-1');assert (c['Id'],c['State']['Pid'],c['Image'])==(b['id'],b['pid'],b['image'])
proof={'runner_image':CANDIDATE,'previous_runner_image':OLD_IMAGE,'worker_sha256':SOURCE_SHA,
 'exact_linux_qualified_image_deployed':True,'linux_runner_tests':23,'old_counterexamples':5,
 'only_maintain_lease_function_changed':True,'only_compose_runner_image_changed':True,
 'controller_postgres_and_daemon_restarted':False,'runner_profile_unchanged':True,
 'local_cutoff_seconds':45,'server_lease_seconds':90,'graphato_source_or_tests_changed':False,'production_modified':False}
save(work/'deployment-proof.json',proof);state['phase']='verified';save(work/'state.json',state);print(json.dumps(proof))
'''


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resume-prepared', action='store_true')
    args = parser.parse_args()
    assert args.apply
    proof = json.loads((FOLDER / 'qualification-proof.json').read_text())
    assert proof['all_passed'] and proof['linux_runner_tests'] == 23 and proof['old_counterexamples'] == 5
    assert vm.digest(FOLDER / 'worker.py') == proof['worker_sha256']
    idle()
    marker = FOLDER / 'deployment-start.json'
    assert marker.exists() == args.resume_prepared and not (FOLDER / 'deployment-proof.json').exists()
    guard = json.loads(marker.read_text())['production_guard_before'] if marker.exists() else begin(FOLDER, 'runner-cadence-deployment')
    if not marker.exists():
        marker.write_text(json.dumps({'production_guard_before': guard}) + '\n')
    values = {'OLD_IMAGE': OLD_IMAGE, 'CANDIDATE': proof['candidate_image'], 'SOURCE_SHA': proof['worker_sha256'], 'RESUME': args.resume_prepared}
    program = ''.join(k + '=' + repr(v) + '\n' for k, v in values.items()) + PROGRAM
    (FOLDER / 'deployment-program.py').write_text(program)
    deployed = json.loads(vm.remote(program, sudo=True, timeout=300))
    (FOLDER / 'deployment-proof.json').write_text(json.dumps(deployed, indent=2) + '\n')
    finish(FOLDER, 'runner-cadence-deployment', guard)
    print(json.dumps(deployed))


if __name__ == '__main__':
    main()
