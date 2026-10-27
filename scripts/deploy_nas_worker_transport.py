"""Install the exact qualified diagnostic worker in the idle owned test stack."""

import copy
import inspect
import json
import tomllib

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from qualify_nas_worker_transport import BASE, FOLDER, OLD_IMAGE


def updated_config(text, candidate):
    config = tomllib.loads(text)
    profile = config['profiles']['graphato']
    assert profile['image'] == OLD_IMAGE
    assert 'LEROY_LEASE_TRACE' not in profile.get('environment', {})
    start = text.index('[profiles.graphato]')
    end = text.find('\n[', start + len('[profiles.graphato]'))
    end = len(text) if end < 0 else end
    block = text[start:end]
    assert block.count(OLD_IMAGE) == 1
    after = text[:start] + block.replace(OLD_IMAGE, candidate) + text[end:]
    if '[profiles.graphato.environment]' in after:
        marker = '[profiles.graphato.environment]'
        after = after.replace(marker, marker + '\nLEROY_LEASE_TRACE = "1"', 1)
    elif 'environment' in profile:
        import re

        block, count = re.subn(r'(\benvironment\s*=\s*\{)', r'\1 LEROY_LEASE_TRACE = "1", ', block, count=1)
        assert count == 1, 'Expected an explicit inline environment or environment table'
        after = text[:start] + block.replace(OLD_IMAGE, candidate) + text[end:]
    else:
        after += '\n[profiles.graphato.environment]\nLEROY_LEASE_TRACE = "1"\n'
    expected = copy.deepcopy(config)
    expected['profiles']['graphato']['image'] = candidate
    expected['profiles']['graphato'].setdefault('environment', {})['LEROY_LEASE_TRACE'] = '1'
    assert tomllib.loads(after) == expected, 'Unrelated runner configuration changed'
    return after


PROGRAM = r'''
import copy,hashlib,json,os,pathlib,subprocess,tomllib
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
def call(args,timeout=30):
 r=subprocess.run(args,capture_output=True,timeout=timeout)
 assert r.returncode==0,'Owned diagnostic installation failed; inspect the protected journal'
 return r.stdout
def inspect(name):return json.loads(call(['docker','inspect',name]))[0]
def digest(data):return hashlib.sha256(data).hexdigest()
def save(path,value):
 temporary=path.with_suffix(path.suffix+'.pending');assert not temporary.exists()
 with temporary.open('x') as f:
  os.chmod(temporary,0o600);json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 temporary.replace(path);fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
services={n:inspect('leroy-nas-parity-'+n+'-1') for n in ('controller','postgres','runner','docker')}
prefix=['docker','exec',services['docker']['Id'],'docker']
assert all(c['State']['Running'] and c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' for c in services.values())
assert call(prefix+['inspect','jenkins-parity','--format','{{.State.Running}}']).decode().strip()=='false'
assert not call(prefix+['ps','-aq','--filter','label=io.leroy.runner=runner-nas-parity']).strip()
for c in json.loads(call(['docker','inspect','paperless','sonarr','radarr','sabnzbd','plex','yt-downloader-service','mail-ingest-service'])):
 assert c['State']['Running'] and c['State'].get('Health',{}).get('Status') in (None,'healthy')
qualified=json.loads((root/'worker-transport-qualification-20261014/validation.json').read_text())
assert qualified['all_passed'] and qualified['linux_worker_tests']==28 and qualified['failures_or_skips']==0
assert qualified['candidate_image']==CANDIDATE and qualified['worker_sha256']==NEW_SHA and qualified['lease_trace_sha256']==TRACE_SHA
old=json.loads(call(prefix+['image','inspect',OLD_IMAGE]))[0];new=json.loads(call(prefix+['image','inspect',CANDIDATE]))[0]
assert new['Config']==old['Config'] and new['RootFS']['Layers'][:-1]==old['RootFS']['Layers']
work=root/'worker-transport-deployment-20261014';path=root/'config/runner.toml'
if not RESUME:
 assert not work.exists();work.mkdir(mode=0o700)
 before=path.read_bytes();after=updated_config(before.decode(),CANDIDATE).encode()
 for name,data in [('runner-before.toml',before),('runner-after.toml',after)]:
  with (work/name).open('xb') as f:os.chmod(work/name,0o600);f.write(data);f.flush();os.fsync(f.fileno())
 runner=services['runner']
 state={'phase':'prepared','candidate':CANDIDATE,'worker_sha256':NEW_SHA,'lease_trace_sha256':TRACE_SHA,
  'old_config_sha256':digest(before),'new_config_sha256':digest(after),
  'runner_id':runner['Id'],'runner_image':runner['Image'],'runner_pid':runner['State']['Pid'],
  'runner_started_at':runner['State']['StartedAt'],
  'runner_configuration_sha256':digest(json.dumps({k:runner[k] for k in ('Config','HostConfig')},sort_keys=True).encode()),
  'other_services':{n:{'id':c['Id'],'pid':c['State']['Pid'],'image':c['Image']} for n,c in services.items() if n!='runner'}}
 save(work/'state.json',state)
else:
 state=json.loads((work/'state.json').read_text());assert state['candidate']==CANDIDATE and state['worker_sha256']==NEW_SHA and state['lease_trace_sha256']==TRACE_SHA
 before=(work/'runner-before.toml').read_bytes();after=(work/'runner-after.toml').read_bytes()
 assert digest(before)==state['old_config_sha256'] and digest(after)==state['new_config_sha256']
assert digest(path.read_bytes()) in {state['old_config_sha256'],state['new_config_sha256']}
if path.read_bytes()==before:
 stat=path.stat();temporary=path.with_suffix('.transport.tmp');assert not temporary.exists()
 with temporary.open('xb') as f:
  os.chmod(temporary,stat.st_mode&0o777);os.chown(temporary,stat.st_uid,stat.st_gid);f.write(after);f.flush();os.fsync(f.fileno())
 assert path.read_bytes()==before;temporary.replace(path);fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
state['phase']='profile_updated';save(work/'state.json',state)
runner=inspect('leroy-nas-parity-runner-1');assert runner['Id']==state['runner_id'] and runner['Image']==state['runner_image']
if (runner['State']['Pid'],runner['State']['StartedAt'])==(state['runner_pid'],state['runner_started_at']):
 call(['docker','restart','--time','30',runner['Id']],timeout=60)
current=inspect('leroy-nas-parity-runner-1')
assert current['State']['Running'] and not current['State']['OOMKilled']
assert (current['State']['Pid'],current['State']['StartedAt'])!=(state['runner_pid'],state['runner_started_at'])
assert digest(json.dumps({k:current[k] for k in ('Config','HostConfig')},sort_keys=True).encode())==state['runner_configuration_sha256']
mount=next(m for m in current['Mounts'] if m['Source']==str(path))
assert digest(call(['docker','exec',current['Id'],'cat',mount['Destination']]))==state['new_config_sha256']
for name,before in state['other_services'].items():
 c=inspect('leroy-nas-parity-'+name+'-1');assert c['Id']==before['id'] and c['Image']==before['image'] and c['State']['Pid']==before['pid']
proof={'worker_image':CANDIDATE,'previous_worker_image':OLD_IMAGE,'worker_sha256':NEW_SHA,'lease_trace_sha256':TRACE_SHA,
 'exact_linux_qualified_image_deployed':True,'linux_worker_tests':28,'changed_profile_fields':['graphato.image','graphato.environment.LEROY_LEASE_TRACE'],
 'only_diagnostic_modules_layer_added':True,'local_cutoff_seconds':45,'server_lease_seconds':90,
 'request_timeouts_or_retries_changed':False,'runner_restarted':True,'controller_postgres_and_daemon_restarted':False,
 'graphato_source_or_tests_changed':False,'production_modified':False}
state['phase']='verified';save(work/'state.json',state);save(work/'deployment-proof.json',proof);print(json.dumps(proof))
'''


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resume-prepared', action='store_true')
    args = parser.parse_args()
    assert args.apply
    closed = json.loads((BASE / 'resource-window-original-night-20261014-b/window-result.json').read_text())
    assert closed['all_seven_original_services_restored_healthy'] and closed['healthy_before_deadline']
    proof = json.loads((FOLDER / 'qualification-proof.json').read_text())
    assert proof['all_passed'] and proof['linux_worker_tests'] == 28 and proof['failures_or_skips'] == 0
    assert vm.digest(vm.ROOT / 'src/leroy/worker.py') == proof['worker_sha256']
    assert vm.digest(vm.ROOT / 'src/leroy/lease_trace.py') == proof['lease_trace_sha256']
    idle()
    marker = FOLDER / 'deployment-start.json'
    assert marker.exists() == args.resume_prepared
    assert not (FOLDER / 'deployment-proof.json').exists()
    guard = json.loads(marker.read_text())['production_guard_before'] if marker.exists() else begin(FOLDER, 'worker-transport-deployment')
    if not marker.exists():
        marker.write_text(json.dumps({'production_guard_before': guard, 'candidate': proof['candidate_image']}) + '\n')
    values = {'OLD_IMAGE': OLD_IMAGE, 'CANDIDATE': proof['candidate_image'], 'NEW_SHA': proof['worker_sha256'],
              'TRACE_SHA': proof['lease_trace_sha256'], 'RESUME': args.resume_prepared}
    program = ''.join(name + '=' + repr(value) + '\n' for name, value in values.items())
    program += 'import copy,tomllib\n' + inspect.getsource(updated_config) + '\n' + PROGRAM
    (FOLDER / 'deployment-program.py').write_text(program)
    deployed = json.loads(vm.remote(program, sudo=True, timeout=240))
    (FOLDER / 'deployment-proof.json').write_text(json.dumps(deployed, indent=2) + '\n')
    finish(FOLDER, 'worker-transport-deployment', guard)
    print(json.dumps(deployed))


if __name__ == '__main__':
    main()
