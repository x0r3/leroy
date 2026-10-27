"""Update only the idle owned NAS test runner, preserving images and configuration."""
import argparse
import hashlib
import json
import tarfile
from datetime import datetime, timezone

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, upload_file

PROGRAM = r'''
import hashlib,json,pathlib,subprocess,tarfile,tomllib
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert root.resolve()==root and (root/'.leroy-owned').is_file()
def inspect(name):
 return json.loads(subprocess.check_output(['docker','inspect',name],text=True,timeout=30))[0]
old=inspect('leroy-nas-parity-runner-1')
assert old['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
assert old['Image']==EXPECTED_IMAGE and old['State']['Running']
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
outer=inspect('leroy-nas-parity-docker-1')
assert outer['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
inner=['docker','exec',outer['Id'],'docker']
assert subprocess.check_output(inner+['inspect','jenkins-parity','--format','{{.State.Running}}'],text=True,timeout=30).strip()=='false'
assert not subprocess.check_output(inner+['ps','-a','--filter','label=io.leroy.runner=runner-nas-parity','-q'],text=True,timeout=30).strip()
services={s:inspect('leroy-nas-parity-'+s+'-1')['Image'] for s in ('postgres','controller','docker')}
worker_ref=tomllib.loads((root/'config/runner.toml').read_text())['profiles']['graphato']['image']
worker=json.loads(subprocess.check_output(inner+['image','inspect',worker_ref],text=True,timeout=30))[0]['Id']
configuration={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
 [root/'compose.yaml',root/'compose.override.yaml',root/'config/runner.toml',root/'config/leroy.toml',root/'config/controller.env']}
context=root/'runner-startup-20261012'
assert not context.exists(), 'Inspect an uncertain deployment before retrying'
context.mkdir(mode=0o700)
bundle=root/'runner-startup-20261012.tar'
with tarfile.open(bundle) as archive:
 members=archive.getmembers()
 assert {m.name for m in members}==set(EXPECTED) and all(m.isfile() and m.size<1024**2 for m in members)
 for member in members:
  data=archive.extractfile(member).read()
  assert hashlib.sha256(data).hexdigest()==EXPECTED[member.name]
  with (context/member.name).open('xb') as output:output.write(data)
base='leroy-runner:nas-parity-before-startup-20261012'
tag='leroy-runner:nas-parity-startup-20261012'
for candidate in (base,tag):
 assert subprocess.run(['docker','image','inspect',candidate],capture_output=True,timeout=30).returncode!=0
subprocess.run(['docker','tag',old['Image'],base],check=True,capture_output=True,timeout=30)
target=subprocess.check_output(['docker','exec',old['Id'],'python','-c','import pathlib,leroy.runner;print(pathlib.Path(leroy.runner.__file__).parent)'],text=True,timeout=30).strip()
assert target.startswith('/usr/local/lib/python3.') and target.endswith('/site-packages/leroy')
dockerfile='FROM '+base+'\nCOPY runner.py worker.py '+target+'/\n'
subprocess.run(['docker','build','--network=none','--pull=false','-t',tag,'-f','-',str(context)],
 input=dockerfile,text=True,check=True,capture_output=True,timeout=240)
image=json.loads(subprocess.check_output(['docker','image','inspect',tag],text=True,timeout=30))[0]
before=json.loads(subprocess.check_output(['docker','image','inspect',old['Image']],text=True,timeout=30))[0]
assert image['Config']==before['Config'] and image['RootFS']['Layers'][:-1]==before['RootFS']['Layers']
code="import hashlib,pathlib,leroy.runner,leroy.worker,json;print(json.dumps({m.__name__.split('.')[-1]+'.py':hashlib.sha256(pathlib.Path(m.__file__).read_bytes()).hexdigest() for m in (leroy.runner,leroy.worker)}))"
actual=json.loads(subprocess.check_output(['docker','run','--rm','--network','none','--memory','128m',
 '--memory-swap','128m',tag,'python','-c',code],text=True,timeout=60))
assert actual==EXPECTED
subprocess.run(['docker','tag',image['Id'],'leroy-runner:nas-parity'],check=True,capture_output=True,timeout=30)
subprocess.run(['docker','compose','up','-d','--no-deps','runner'],cwd=root,check=True,capture_output=True,timeout=180)
after=inspect('leroy-nas-parity-runner-1')
assert after['State']['Running'] and after['Image']==image['Id']
for key in ('Env','Cmd','Entrypoint','WorkingDir','User'):
 assert (sorted(after['Config'][key])==sorted(old['Config'][key]) if key=='Env' else after['Config'].get(key)==old['Config'].get(key))
for key in ('Memory','MemorySwap','NanoCpus','NetworkMode','RestartPolicy'):
 assert after['HostConfig'][key]==old['HostConfig'][key]
mounts=lambda c:sorted([{k:m[k] for k in ('Type','Source','Destination','RW')} for m in c['Mounts']],key=lambda m:m['Destination'])
assert mounts(after)==mounts(old)
assert json.loads(subprocess.check_output(['docker','exec',after['Id'],'python','-c',code],text=True,timeout=30))==EXPECTED
assert services=={s:inspect('leroy-nas-parity-'+s+'-1')['Image'] for s in services}
assert worker==json.loads(subprocess.check_output(inner+['image','inspect',worker_ref],text=True,timeout=30))[0]['Id']
assert configuration=={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in configuration}
print(json.dumps({'previous_runner_image':old['Image'],'runner_image':image['Id'],
 'module_sha256':actual,'old_runner_image_retained':True,'image_configuration_unchanged':True,
 'dependencies_unchanged':True,'runner_environment_resources_and_mounts_unchanged':True,
 'controller_postgres_daemon_and_job_worker_images_unchanged':True,
 'configuration_sha256':configuration,'graphato_sources_tests_and_deadlines_changed':False,
 'production_modified':False}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    assert parser.parse_args().apply
    folder = ROOT/'test-results/nas-parity/followup/runner-startup-20261012'
    folder.mkdir(exist_ok=True)
    assert not (folder/'started.json').exists(), 'Inspect the retained first deployment before resuming'
    closed = json.loads((folder.parent/'full-release-nas-20261012-l/final-state.json').read_text())
    assert closed['original_ci_parent_runs_finished_both'] and not closed['vm_running']
    idle()
    assert not vm.state()['State']['Running']
    expected = {name+'.py':hashlib.sha256((ROOT/'src/leroy'/(name+'.py')).read_bytes()).hexdigest()
                for name in ('runner','worker')}
    archive = folder/'runner-startup-20261012.tar'
    with tarfile.open(archive,'w') as bundle:
        for name in expected:
            bundle.add(ROOT/'src/leroy'/name,arcname=name)
    before = begin(folder,'runner-startup-deployment')
    (folder/'started.json').write_text(json.dumps({'at':datetime.now(timezone.utc).isoformat(),
        'production_guard_before':before,'source_sha256':expected},indent=2)+'\n',encoding='utf-8')
    upload_file(archive,'/volume1/docker/leroy-nas-parity/'+archive.name,ROOT/'.local/nas-ssh.json')
    old_image = json.loads((folder.parent/'full-release-nas-20261012-l/infrastructure-after.json').read_text())['services']['runner']['image']
    value = json.loads(vm.remote('EXPECTED='+repr(expected)+'\nEXPECTED_IMAGE='+repr(old_image)+'\n'+PROGRAM,
                                sudo=True,timeout=600))
    value.update(at=datetime.now(timezone.utc).isoformat())
    (folder/'deployment-proof.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    finish(folder,'runner-startup-deployment',before)
    print(json.dumps(value))


if __name__=='__main__':
    main()
