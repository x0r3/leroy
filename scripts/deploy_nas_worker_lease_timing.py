"""Add qualified passive lease timing to the idle NAS test worker only."""

import argparse
import json
import tarfile

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, upload_file

PROGRAM = r'''
import hashlib,json,os,pathlib,re,subprocess,tomllib
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
def inspect(name):return json.loads(subprocess.check_output(['docker','inspect',name],text=True,timeout=20))[0]
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
outer=inspect('leroy-nas-parity-docker-1');prefix=['docker','exec',outer['Id'],'docker']
assert outer['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
assert subprocess.check_output(prefix+['inspect','jenkins-parity','--format','{{.State.Running}}'],text=True).strip()=='false'
assert not subprocess.check_output(prefix+['ps','-aq','--filter','label=io.leroy.runner=runner-nas-parity'],text=True).strip()
services={s:{k:inspect('leroy-nas-parity-'+s+'-1')[k] for k in ('Id','Image','State')} for s in ('controller','postgres','docker')}
path=root/'config/runner.toml';before=path.read_text();stat=path.stat();config=tomllib.loads(before)
old=config['profiles']['graphato']['image'];assert old==OLD_IMAGE
probe=['run','--rm','--network','none','--memory','128m','--memory-swap','128m','--cpus','0.5','--entrypoint','python']
code="import hashlib,json,pathlib,leroy.worker;p=pathlib.Path(leroy.worker.__file__);print(json.dumps({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))"
original=json.loads(subprocess.check_output(prefix+probe+[old,'-c',code],text=True,timeout=60))
assert original['sha256']==OLD_SHA
assert re.fullmatch(r'/opt/leroy-worker/lib/python3\.\d+/site-packages/leroy/worker.py',original['path'])
context='/var/lib/docker/leroy-worker-lease-timing-20261014';tag='leroy-job:nas-lease-timing-20261014'
assert subprocess.run(prefix+['image','inspect',tag],capture_output=True).returncode!=0
exists=subprocess.run(['docker','exec',outer['Id'],'test','-e',context],capture_output=True).returncode==0
if exists:
 assert RESUME
 actual=subprocess.check_output(['docker','exec',outer['Id'],'sha256sum',context+'/worker.py'],text=True).split()[0]
 assert actual==NEW_SHA
else:
 with (root/'worker-lease-timing-20261014.tar').open('rb') as stream:
  subprocess.run(['docker','exec','-i',outer['Id'],'sh','-c','umask 077; mkdir '+context+' && tar -xf - -C '+context],stdin=stream,check=True,capture_output=True,timeout=30)
base='leroy-job:nas-before-lease-timing-20261014'
base_probe=subprocess.run(prefix+['image','inspect',base],capture_output=True,text=True)
if base_probe.returncode:subprocess.run(prefix+['tag',old,base],check=True,capture_output=True,timeout=20)
else:
 assert RESUME
 assert json.loads(base_probe.stdout)[0]['Id']==json.loads(subprocess.check_output(prefix+['image','inspect',old],text=True))[0]['Id']
subprocess.run(['docker','exec','-i',outer['Id'],'docker','build','--network=none','--pull=false','-t',tag,'-f','-',context],
 input='FROM '+base+'\nCOPY worker.py '+original['path']+'\n',text=True,check=True,capture_output=True,timeout=120)
old_info=json.loads(subprocess.check_output(prefix+['image','inspect',old],text=True))[0]
new=json.loads(subprocess.check_output(prefix+['image','inspect',tag],text=True))[0]
assert new['Config']==old_info['Config'] and new['RootFS']['Layers'][:-1]==old_info['RootFS']['Layers']
actual=json.loads(subprocess.check_output(prefix+probe+[new['Id'],'-c',code],text=True,timeout=60))
assert actual['sha256']==NEW_SHA and actual['path']==original['path']
start=before.index('[profiles.graphato]');end=before.find('\n[',start+len('[profiles.graphato]'));end=len(before) if end<0 else end
block=before[start:end];assert block.count(old)==1
after=before[:start]+block.replace(old,new['Id'])+before[end:]
candidate=tomllib.loads(after);candidate['profiles']['graphato']['image']=old;assert candidate==config
backup=root/'config/runner-before-lease-timing-20261014.toml';assert not backup.exists()
with backup.open('x') as stream:os.chmod(backup,0o600);stream.write(before);stream.flush();os.fsync(stream.fileno())
temporary=path.with_suffix('.lease-timing.tmp');assert not temporary.exists() and path.read_text()==before
with temporary.open('x') as stream:
 os.chmod(temporary,stat.st_mode&0o777);os.chown(temporary,stat.st_uid,stat.st_gid)
 stream.write(after);stream.flush();os.fsync(stream.fileno())
temporary.replace(path)
runner=inspect('leroy-nas-parity-runner-1')
subprocess.run(['docker','restart','--time','30',runner['Id']],check=True,capture_output=True,timeout=60)
current=inspect('leroy-nas-parity-runner-1')
assert current['Id']==runner['Id'] and current['Image']==runner['Image'] and current['State']['Running']
assert current['Config']==runner['Config'] and current['HostConfig']==runner['HostConfig']
for s,prior in services.items():
 current=inspect('leroy-nas-parity-'+s+'-1')
 assert current['Id']==prior['Id'] and current['Image']==prior['Image'] and current['State']['Pid']==prior['State']['Pid']
print(json.dumps({'previous_worker_image':old,'worker_image':new['Id'],'previous_worker_sha256':OLD_SHA,
 'worker_sha256':NEW_SHA,'image_configuration_unchanged':True,'base_layers_retained':True,
 'changed_profile_fields':['graphato.image'],'lease_decisions_and_deadlines_changed':False,
 'runner_restarted':True,'controller_postgres_and_daemon_restarted':False,
 'graphato_source_or_tests_changed':False,'production_modified':False}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resume-prepared', action='store_true')
    args = parser.parse_args()
    assert args.apply
    folder = ROOT / 'test-results/nas-parity/followup/worker-lease-timing-20261014'
    before = json.loads((folder / 'before.json').read_text())
    proof = json.loads((folder / 'semantic-equivalence.json').read_text())
    source = ROOT / 'src/leroy/worker.py'
    assert proof['lease_behavior_unchanged'] and proof['other_worker_code_unchanged']
    assert proof['new_worker_sha256'] == vm.digest(source)
    marker = folder / 'deployment-start.json'
    assert not (folder / 'deployment-proof.json').exists(), 'Retain completed deployment evidence'
    assert args.resume_prepared == marker.exists(), 'Inspect an uncertain deployment before explicitly resuming'
    idle()
    assert not vm.state()['State']['Running']
    if marker.exists():
        retained = json.loads(marker.read_text())
        assert retained['source_sha256'] == vm.digest(source)
        guard = retained['production_guard_before']
    else:
        guard = begin(folder, 'worker-lease-timing')
        marker.write_text(json.dumps({'production_guard_before': guard, 'source_sha256': vm.digest(source)}) + '\n')
    archive = folder / 'worker-lease-timing-20261014.tar'
    with tarfile.open(archive, 'w') as bundle:
        bundle.add(source, arcname='worker.py')
    upload_file(archive, '/volume1/docker/leroy-nas-parity/' + archive.name, vm.CREDENTIALS)
    code = 'OLD_IMAGE=' + repr(before['image']) + '\nOLD_SHA=' + repr(before['sha256']) + '\nNEW_SHA=' + repr(vm.digest(source)) + '\nRESUME=' + repr(args.resume_prepared) + '\n'
    value = json.loads(vm.remote(code + PROGRAM, sudo=True, timeout=360))
    (folder / 'deployment-proof.json').write_text(json.dumps(value, indent=2) + '\n')
    finish(folder, 'worker-lease-timing', guard)
    print(json.dumps(value))


if __name__ == '__main__':
    main()
