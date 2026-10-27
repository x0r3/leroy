"""Qualify a diagnostic-only worker layer after the NAS comparison is closed."""

import json
import shutil
import tarfile

import nas_release_vm as vm
from nas_followup_support import inner
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, upload_file

BASE = ROOT / 'test-results/nas-parity/followup'
FOLDER = BASE / 'worker-transport-candidate-20261014'
OLD_IMAGE = 'sha256:0beba2d521cb061818bbf18295ab0329094d31092b4a2cbd8cfa24dca2cf74dc'
OLD_SHA = '62e0bb95efa87469a8677aaf91c198b840f3b14dbabb79e3742ac0d50b86b938'

PROGRAM = r'''
import hashlib,json,os,pathlib,re,subprocess,tarfile,time,tomllib,xml.etree.ElementTree as ET
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
def call(args,timeout=30,**kw):
 r=subprocess.run(args,capture_output=True,timeout=timeout,**kw)
 assert r.returncode==0,'Scoped diagnostic qualification failed; inspect protected evidence'
 return r.stdout
def inspect(name):return json.loads(call(['docker','inspect',name]))[0]
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
services={name:inspect('leroy-nas-parity-'+name+'-1') for name in ('controller','postgres','runner','docker')}
assert all(c['State']['Running'] and c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' for c in services.values())
prefix=['docker','exec',services['docker']['Id'],'docker']
assert call(prefix+['inspect','jenkins-parity','--format','{{.State.Running}}']).decode().strip()=='false'
assert not call(prefix+['ps','-q','--filter','label=io.leroy.runner=runner-nas-parity']).strip()
assert tomllib.loads((root/'config/runner.toml').read_text())['profiles']['graphato']['image']==OLD_IMAGE
for c in json.loads(call(['docker','inspect','paperless','sonarr','radarr','sabnzbd','plex','yt-downloader-service','mail-ingest-service'])):
 assert c['State']['Running'] and c['State'].get('Health',{}).get('Status') in (None,'healthy')
work=root/'worker-transport-qualification-20261014';assert not work.exists();work.mkdir(mode=0o700)
source=root/'worker-transport-candidate-20261014.tar';assert hashlib.sha256(source.read_bytes()).hexdigest()==ARCHIVE_SHA
with tarfile.open(source) as bundle:
 members=bundle.getmembers();assert len(members)==len(EXPECTED) and {m.name for m in members}==set(EXPECTED)
 for member in members:
  assert member.isfile() and member.name==pathlib.PurePosixPath(member.name).name and member.size<=24*1024**2
  assert hashlib.sha256(bundle.extractfile(member).read()).hexdigest()==EXPECTED[member.name]
probe=['run','--rm','--network','none','--memory','128m','--memory-swap','128m','--cpus','0.5','--entrypoint','python']
identity_code="import hashlib,json,pathlib,leroy.worker,httpx,httpcore;p=pathlib.Path(leroy.worker.__file__);print(json.dumps({'path':str(p),'worker_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'httpx':httpx.__version__,'httpcore':httpcore.__version__}))"
old_identity=json.loads(call(prefix+probe+[OLD_IMAGE,'-c',identity_code],timeout=60))
assert old_identity['worker_sha256']==OLD_SHA
assert re.fullmatch(r'/opt/leroy-worker/lib/python3\.\d+/site-packages/leroy/worker.py',old_identity['path'])
context='/var/lib/docker/leroy-worker-transport-20261014';tag='leroy-job:nas-transport-trace-20261014';base='leroy-job:nas-before-transport-trace-20261014'
assert subprocess.run(prefix+['image','inspect',tag],capture_output=True).returncode!=0
assert subprocess.run(prefix+['image','inspect',base],capture_output=True).returncode!=0
assert subprocess.run(['docker','exec',services['docker']['Id'],'test','-e',context],capture_output=True).returncode!=0
with source.open('rb') as stream:
 call(['docker','exec','-i',services['docker']['Id'],'sh','-c','umask 022; mkdir '+context+' && tar -xf - -C '+context+' && chmod 755 '+context+' && chmod 644 '+context+'/* && mkdir '+context+'/results && chown 10001:10001 '+context+'/results && chmod 750 '+context+'/results'],stdin=stream)
call(prefix+['tag',OLD_IMAGE,base])
package=str(pathlib.PurePosixPath(old_identity['path']).parent)+'/'
dockerfile='FROM '+base+'\nCOPY worker.py lease_trace.py '+package+'\n'
call(['docker','exec','-i',services['docker']['Id'],'docker','build','--network=none','--pull=false','-t',tag,'-f','-',context],input=dockerfile.encode(),timeout=120)
old=json.loads(call(prefix+['image','inspect',OLD_IMAGE]))[0];new=json.loads(call(prefix+['image','inspect',tag]))[0]
assert new['Config']==old['Config'] and new['RootFS']['Layers'][:-1]==old['RootFS']['Layers']
current_identity=json.loads(call(prefix+probe+[new['Id'],'-c',identity_code],timeout=60));assert current_identity['worker_sha256']==EXPECTED['worker.py']
common=prefix+['run','--rm','--init','--user','10001:10001','--network','none','--read-only','--cap-drop','ALL',
 '--security-opt','no-new-privileges:true','--memory','256m','--memory-swap','256m','--cpus','1','--pids-limit','128',
 '--tmpfs','/tmp:rw,nosuid,size=64m,mode=1777','--mount','type=bind,src='+context+',dst=/operator,readonly',
 '--mount','type=bind,src='+context+'/results,dst=/results','-e','PYTHONPATH=/operator/pytest-runtime.zip',
 '-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTEST_DISABLE_PLUGIN_AUTOLOAD=1',
 '--name','leroy-worker-transport-qualification-20261014','--label','io.leroy.operator-test=worker-transport-20261014',
 '--entrypoint','python']
result=None
try:
 test=subprocess.run(common+['-e','LEROY_LEASE_TRACE=1',new['Id'],'-m','pytest','/operator/test_heartbeat.py',
  '/operator/test_lease_transport_trace.py','-k','not docker_operations','-q','-p','no:cacheprovider','--junitxml=/results/current.xml'],capture_output=True,timeout=180)
 (work/'tests.log').write_bytes(test.stdout+b'\n'+test.stderr)
 raw=call(['docker','exec',services['docker']['Id'],'cat',context+'/results/current.xml']);(work/'current.xml').write_bytes(raw)
 cases=ET.fromstring(raw).findall('.//testcase');bad=sum(any(c.find(k) is not None for k in ('failure','error','skipped')) for c in cases)
 result={'candidate_image':new['Id'],'previous_image':OLD_IMAGE,'worker_sha256':EXPECTED['worker.py'],
  'lease_trace_sha256':EXPECTED['lease_trace.py'],'linux_worker_tests':len(cases),'failures_or_skips':bad,
  'all_passed':test.returncode==0 and len(cases)==28 and bad==0,'worker_identity':current_identity,
  'only_diagnostic_modules_layer_added':True,'image_configuration_unchanged':True,'runtime_pytest_added':False,
  'trace_flag_enabled_during_tests':True,'local_cutoff_seconds':45,'server_lease_seconds':90,
  'request_timeouts_or_retries_changed':False,'runner_config_changed':False,'production_modified':False}
 (work/'validation.json').write_text(json.dumps(result,indent=2)+'\n');(work/'validation.json').chmod(0o600)
finally:
 ids=call(prefix+['ps','-aq','--filter','label=io.leroy.operator-test=worker-transport-20261014']).decode().split()
 for identity in ids:
  info=json.loads(call(prefix+['inspect',identity]))[0]
  assert info['Image']==new['Id'] and info['Config']['Labels']['io.leroy.operator-test']=='worker-transport-20261014'
  if info['State']['Running']:call(prefix+['stop','--time','10',identity],timeout=20)
  if subprocess.run(prefix+['inspect',identity],capture_output=True).returncode==0:call(prefix+['rm',identity])
for name,before in services.items():
 after=inspect('leroy-nas-parity-'+name+'-1');assert before['Id']==after['Id'] and before['State']['Pid']==after['State']['Pid'] and before['Image']==after['Image']
print(json.dumps(result));assert result['all_passed'],'Diagnostic qualification failed; running configuration unchanged'
'''


def main():
    result = json.loads((BASE / 'resource-window-original-night-20261014-b/window-result.json').read_text())
    assert result['all_seven_original_services_restored_healthy'] and result['healthy_before_deadline']
    idle()
    assert not vm.state()['State']['Running']
    assert inner('inspect', 'jenkins-parity', '--format', '{{.State.Running}}').strip() == 'false'
    assert not (FOLDER / 'qualification-start.json').exists(), 'Inspect the retained qualification before any resume'
    inputs = FOLDER / 'qualification-inputs'
    inputs.mkdir()
    for name, source in [('worker.py', FOLDER / 'worker.py'), ('lease_trace.py', FOLDER / 'lease_trace.py'),
                         ('test_heartbeat.py', ROOT / 'tests/test_heartbeat.py'),
                         ('test_lease_transport_trace.py', ROOT / 'tests/test_lease_transport_trace.py'),
                         ('pytest-runtime.zip', BASE / 'controller-reconcile-locks-20261014/pytest-runtime.zip')]:
        shutil.copy2(source, inputs / name)
    expected = {p.name: vm.digest(p) for p in inputs.iterdir()}
    archive = FOLDER / 'qualification-inputs.tar'
    with tarfile.open(archive, 'w') as bundle:
        for path in inputs.iterdir():
            bundle.add(path, arcname=path.name)
    before = begin(FOLDER, 'worker-transport-qualification')
    (FOLDER / 'qualification-start.json').write_text(json.dumps({'production_guard_before': before, 'inputs_sha256': expected}) + '\n')
    upload_file(archive, '/volume1/docker/leroy-nas-parity/worker-transport-candidate-20261014.tar', vm.CREDENTIALS, timeout=120)
    constants = {'OLD_IMAGE': OLD_IMAGE, 'OLD_SHA': OLD_SHA, 'ARCHIVE_SHA': vm.digest(archive), 'EXPECTED': expected}
    program = ''.join(name + '=' + repr(value) + '\n' for name, value in constants.items()) + PROGRAM
    (FOLDER / 'qualification-program.py').write_text(program)
    proof = json.loads(vm.remote(program, sudo=True, timeout=480))
    (FOLDER / 'qualification-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    finish(FOLDER, 'worker-transport-qualification', before)
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
