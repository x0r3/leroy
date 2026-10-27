"""Install the tested child-cancellation reason in the idle NAS test profile only."""

import json
import tarfile
from contextlib import closing
from datetime import datetime, timezone

import nas_release_vm as vm
from compare_nas_antares import client
from nas_ssh import ROOT, upload_file


def main():
    folder = ROOT / 'test-results/nas-parity/followup/full-release-nas-20261011-d'
    destination = folder / 'lease-reason-deployment.json'
    assert not destination.exists(), 'Retain the first image update'
    assert not vm.state()['State']['Running']
    with closing(client()) as api:
        assert not any(p['enabled'] for p in api.get('/api/pipelines').json())
        assert not any(r['status'] in {'running', 'queued', 'waiting'} for r in api.get('/api/runs').json())
    source = ROOT / 'src/leroy/worker.py'
    expected = vm.digest(source)
    proof = json.loads((folder / 'lease-reason-tests.json').read_text())
    assert proof['passed'] and proof['worker_sha256'] == expected and proof['tests_passed'] == 16
    started = folder / 'lease-reason-deployment-started.json'
    if started.exists():
        assert json.loads(started.read_text())['worker_sha256'] == expected
    else:
        started.write_text(json.dumps({'at': datetime.now(timezone.utc).isoformat(),
                                      'worker_sha256': expected, 'original_d_attempts_changed': False}))
    local = ROOT / '.local/nas-lease-reason-20261011.tar'
    with tarfile.open(local, 'w') as bundle:
        bundle.add(source, arcname='worker.py')
    upload_file(local, '/volume1/docker/leroy-nas-parity/lease-reason-20261011.tar', vm.CREDENTIALS)
    program = 'EXPECTED=' + repr(expected) + '\n' + r'''
import hashlib,json,pathlib,re,subprocess,tomllib
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
outer=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-docker-1'],text=True))[0]
assert outer['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
prefix=['docker','exec','-i',outer['Id'],'docker']
assert subprocess.check_output(prefix+['inspect','jenkins-parity','--format','{{.State.Running}}'],text=True).strip()=='false'
assert not subprocess.check_output(prefix+['ps','-a','--filter','label=io.leroy.runner=runner-nas-parity','-q'],text=True).strip()
path=root/'config/runner.toml';before=path.read_text();config=tomllib.loads(before)
old_id=config['profiles']['graphato']['image'];assert re.fullmatch(r'sha256:[0-9a-f]{64}',old_id)
old=json.loads(subprocess.check_output(prefix+['image','inspect',old_id],text=True))[0]
context='/var/lib/docker/leroy-lease-reason-20261011'
context_exists=subprocess.run(['docker','exec',outer['Id'],'test','-d',context],capture_output=True).returncode==0
if context_exists:
 staged=subprocess.check_output(['docker','exec',outer['Id'],'cat',context+'/worker.py'])
 assert hashlib.sha256(staged).hexdigest()==EXPECTED
else:
 with (root/'lease-reason-20261011.tar').open('rb') as stream:
  subprocess.run(['docker','exec','-i',outer['Id'],'sh','-c','mkdir '+context+' && tar -xf - -C '+context],stdin=stream,check=True,timeout=30)
probe=['run','--rm','--network','none','--memory','128m','--memory-swap','128m','--cpus','0.5','--entrypoint','python']
target=subprocess.check_output(prefix+probe+[old_id,'-c','import leroy.worker;print(leroy.worker.__file__)'],text=True,timeout=120).strip()
assert re.fullmatch(r'/opt/leroy-worker/lib/python3\.\d+/site-packages/leroy/worker.py',target)
tag='leroy-job:nas-lease-reason-20261011'
assert subprocess.run(prefix+['image','inspect',tag],capture_output=True).returncode!=0
base='leroy-job:nas-lease-reason-base-20261011'
base_probe=subprocess.run(prefix+['image','inspect',base],capture_output=True,text=True)
if base_probe.returncode:subprocess.run(prefix+['tag',old_id,base],check=True)
else:assert json.loads(base_probe.stdout)[0]['Id']==old_id
subprocess.run(prefix+['build','--network=none','--pull=false','-t',tag,'-f','-',context],input='FROM '+base+'\nCOPY worker.py '+target+'\n',text=True,check=True,stdout=subprocess.DEVNULL,timeout=240)
new=json.loads(subprocess.check_output(prefix+['image','inspect',tag],text=True))[0]
assert old['Config']==new['Config'] and old['RootFS']['Layers']==new['RootFS']['Layers'][:-1]
actual=subprocess.check_output(prefix+probe+[new['Id'],'-c','import hashlib,leroy.worker;print(hashlib.sha256(open(leroy.worker.__file__,"rb").read()).hexdigest())'],text=True,timeout=120).strip()
assert actual==EXPECTED
section='[profiles.graphato]';start=before.index(section);end=before.find('\n[',start+len(section));end=len(before) if end<0 else end
block=before[start:end];assert block.count(old_id)==1
after=before[:start]+block.replace(old_id,new['Id'])+before[end:]
changed=tomllib.loads(after);changed['profiles']['graphato']['image']=old_id;assert changed==config
backup=root/'config/runner-before-lease-reason-20261011.toml';assert not backup.exists();backup.write_text(before)
assert path.read_text()==before;path.write_text(after)
subprocess.run(['docker','restart','--time','30','leroy-nas-parity-runner-1'],check=True,stdout=subprocess.DEVNULL,timeout=60)
print(json.dumps({'before_image':old_id,'after_image':new['Id'],'worker_sha256':actual,'image_config_unchanged':True,'original_image_layers_retained':True,'changed_profile_fields':['graphato.image'],'profile_before_sha256':hashlib.sha256(before.encode()).hexdigest(),'profile_after_sha256':hashlib.sha256(after.encode()).hexdigest(),'owned_runner_restarted':True,'controller_and_database_restarted':False,'graphato_source_or_tests_changed':False,'production_modified':False}))
'''
    result = json.loads(vm.remote(program, timeout=600))
    result.update(at=datetime.now(timezone.utc).isoformat(),
                  original_d_attempts_changed=False, validation='16 targeted worker/heartbeat tests passed')
    destination.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
