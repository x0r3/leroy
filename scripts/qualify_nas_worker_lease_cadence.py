"""Qualify the worker cadence candidate after both NAS windows are restored.

Only an immutable candidate in the owned nested daemon is built. Tests run
without credentials, a Docker socket or external networking. No running Leroy
service or runner configuration is changed.
"""

import argparse
import hashlib
import json
import tarfile

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, upload_file

FOLLOWUP = ROOT / 'test-results/nas-parity/followup'
FOLDER = FOLLOWUP / 'worker-lease-cadence-20261014'
OLD_IMAGE = 'sha256:e20b2a7fb36ab09f72c2b6038e33a971be8409a18bb76fb0f2ee4ce9185bcc79'
OLD_SHA = 'bd4672235dd2cc2cd9e3d30c3d1b690089bed900abee0bb449487b859c90abac'


def require_restored_windows():
    for engine in ('leroy', 'jenkins'):
        path = FOLLOWUP / ('resource-window-reconcile8g-' + engine + '-20261014/window-result.json')
        result = json.loads(path.read_text())
        assert result['all_seven_original_services_restored_healthy'] and result['healthy_before_deadline']


RUNNER_COMPONENT = r'''
def runner_component(work,runner_image):
 payload=work/'runner-operator';payload.mkdir(mode=0o755);payload.chmod(0o755)
 with tarfile.open(source) as bundle:
  for member in bundle:
   assert member.isfile() and member.name in EXPECTED and member.name==pathlib.PurePosixPath(member.name).name
   assert member.size<=24*1024**2
   data=bundle.extractfile(member).read();assert hashlib.sha256(data).hexdigest()==EXPECTED[member.name]
   p=payload/member.name;p.write_bytes(data);p.chmod(0o644)
 results=work/'runner-results';results.mkdir(mode=0o750);os.chown(results,10001,10001)
 label='worker-cadence-runner-20261014';name='leroy-worker-cadence-runner-20261014'
 args=['docker','run','--rm','--init','--name',name,'--label','io.leroy.operator-test='+label,
 '--user','10001:10001','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
 '--memory','256m','--memory-swap','256m','--cpus','1','--pids-limit','128','--tmpfs','/tmp:rw,nosuid,size=64m,mode=1777',
 '--mount','type=bind,src='+str(payload)+',dst=/operator,readonly','--mount','type=bind,src='+str(results)+',dst=/results',
 '-e','PYTHONPATH=/operator/pytest-runtime.zip','-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTEST_DISABLE_PLUGIN_AUTOLOAD=1',
 '--entrypoint','python',runner_image,'-m','pytest','/operator/test_heartbeat.py','-k','docker_operations',
 '-q','-p','no:cacheprovider','--junitxml=/results/runner.xml']
 try:
  test=subprocess.run(args,capture_output=True,timeout=180)
  (work/'runner.log').write_bytes(test.stdout+b'\n'+test.stderr)
  cases=ET.parse(results/'runner.xml').findall('.//testcase')
  ok=test.returncode==0 and len(cases)==1 and all(not any(c.find(k) is not None for k in ('failure','error','skipped')) for c in cases)
  return {'runner_image':runner_image,'linux_runner_tests':len(cases),'runner_test_passed':ok}
 finally:
  probe=subprocess.run(['docker','inspect',name],capture_output=True)
  if probe.returncode==0:
   item=json.loads(probe.stdout)[0];assert item['Image']==runner_image and item['Config']['Labels']['io.leroy.operator-test']==label
   if item['State']['Running']:call(['docker','stop','--time','10',item['Id']],timeout=20)
   if subprocess.run(['docker','inspect',name],capture_output=True).returncode==0:call(['docker','rm',name])
'''

PROGRAM = RUNNER_COMPONENT + r'''
import hashlib,json,os,pathlib,re,subprocess,tarfile,time,tomllib,xml.etree.ElementTree as ET
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
def call(args,timeout=30,**kw):
 r=subprocess.run(args,capture_output=True,timeout=timeout,**kw)
 assert r.returncode==0,'Scoped worker qualification command failed; output withheld'
 return r.stdout
def inspect(name):return json.loads(call(['docker','inspect',name]))[0]
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
names=['controller','postgres','runner','docker']
services={s:inspect('leroy-nas-parity-'+s+'-1') for s in names}
assert all(c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' and c['State']['Running'] for c in services.values())
prefix=['docker','exec',services['docker']['Id'],'docker']
assert call(prefix+['inspect','jenkins-parity','--format','{{.State.Running}}']).decode().strip()=='false'
assert not call(prefix+['ps','-q','--filter','label=io.leroy.runner=runner-nas-parity']).strip()
for c in json.loads(call(['docker','inspect','paperless','sonarr','radarr','sabnzbd','plex','yt-downloader-service','mail-ingest-service'])):
 assert c['State']['Running'] and c['State'].get('Health',{}).get('Status') in (None,'healthy')
assert tomllib.loads((root/'config/runner.toml').read_text())['profiles']['graphato']['image']==OLD_IMAGE
work=root/'worker-lease-cadence-qualification-20261014';assert not work.exists();work.mkdir(mode=0o700)
source=root/'worker-lease-cadence-20261014.tar'
assert hashlib.sha256(source.read_bytes()).hexdigest()==ARCHIVE_SHA
with tarfile.open(source) as bundle:
 members=bundle.getmembers();assert {m.name for m in members}==set(EXPECTED) and len(members)==len(EXPECTED)
 for m in members:
  assert m.isfile() and m.name==pathlib.PurePosixPath(m.name).name and m.size<=24*1024**2
  data=bundle.extractfile(m).read();assert hashlib.sha256(data).hexdigest()==EXPECTED[m.name]
probe=['run','--rm','--network','none','--memory','128m','--memory-swap','128m','--cpus','0.5','--entrypoint','python']
code="import hashlib,json,pathlib,leroy.worker;p=pathlib.Path(leroy.worker.__file__);print(json.dumps({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))"
original=json.loads(call(prefix+probe+[OLD_IMAGE,'-c',code],timeout=60));assert original['sha256']==OLD_SHA
assert re.fullmatch(r'/opt/leroy-worker/lib/python3\.\d+/site-packages/leroy/worker.py',original['path'])
context='/var/lib/docker/leroy-worker-cadence-20261014';tag='leroy-job:nas-lease-cadence-20261014'
assert subprocess.run(prefix+['image','inspect',tag],capture_output=True).returncode!=0
assert subprocess.run(['docker','exec',services['docker']['Id'],'test','-e',context],capture_output=True).returncode!=0
with source.open('rb') as stream:
 call(['docker','exec','-i',services['docker']['Id'],'sh','-c','umask 022; mkdir '+context+' && tar -xf - -C '+context+' && chmod 755 '+context+' && chmod 644 '+context+'/* && mkdir '+context+'/results && chown 10001:10001 '+context+'/results && chmod 750 '+context+'/results'],stdin=stream)
base='leroy-job:nas-before-lease-cadence-20261014'
assert subprocess.run(prefix+['image','inspect',base],capture_output=True).returncode!=0
call(prefix+['tag',OLD_IMAGE,base])
dockerfile='FROM '+base+'\nCOPY worker.py '+original['path']+'\n'
call(['docker','exec','-i',services['docker']['Id'],'docker','build','--network=none','--pull=false','-t',tag,'-f','-',context],input=dockerfile.encode(),timeout=120)
old=json.loads(call(prefix+['image','inspect',OLD_IMAGE]))[0];new=json.loads(call(prefix+['image','inspect',tag]))[0]
assert new['Config']==old['Config'] and new['RootFS']['Layers'][:-1]==old['RootFS']['Layers']
actual=json.loads(call(prefix+probe+[new['Id'],'-c',code],timeout=60));assert actual['sha256']==EXPECTED['worker.py'] and actual['path']==original['path']
common=prefix+['run','--rm','--init','--user','10001:10001','--label','io.leroy.operator-test=worker-cadence-20261014',
 '--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','256m','--memory-swap','256m','--cpus','1','--pids-limit','128',
 '--tmpfs','/tmp:rw,nosuid,size=64m,mode=1777','--mount','type=bind,src='+context+',dst=/operator,readonly',
 '--mount','type=bind,src='+context+'/results,dst=/results','-e','PYTHONPATH=/operator/pytest-runtime.zip','-e','PYTHONDONTWRITEBYTECODE=1',
 '-e','PYTEST_DISABLE_PLUGIN_AUTOLOAD=1','--entrypoint','python']
def read_result(name):
 raw=call(['docker','exec',services['docker']['Id'],'cat',context+'/results/'+name])
 (work/name).write_bytes(raw);return ET.fromstring(raw).findall('.//testcase')
result={};started=time.monotonic()
try:
 argv=['/operator/test_heartbeat.py','-q','-p','no:cacheprovider','-k','successful_request_time_counts_towards_renewal_cadence','--junitxml=/results/old.xml']
 bootstrap="import ast,pathlib,leroy.worker,pytest;s=pathlib.Path('/operator/worker-before.py').read_text();t=ast.parse(s);n=next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name=='maintain_lease');exec(compile(ast.get_source_segment(s,n),'original-worker','exec'),leroy.worker.__dict__);raise SystemExit(pytest.main("+repr(argv)+"))"
 baseline=subprocess.run(common+['--name','leroy-worker-cadence-baseline-20261014',new['Id'],'-c',bootstrap],capture_output=True,timeout=180)
 (work/'old.log').write_bytes(baseline.stdout+b'\n'+baseline.stderr)
 cases=read_result('old.xml');assert baseline.returncode==1 and len(cases)==5 and all(c.find('failure') is not None for c in cases),'Original worker did not reproduce all five intended cadence failures'
 current=subprocess.run(common+['--name','leroy-worker-cadence-current-20261014',new['Id'],'-m','pytest','/operator/test_heartbeat.py','-q','-p','no:cacheprovider','-k','not docker_operations','--junitxml=/results/current.xml'],capture_output=True,timeout=180)
 (work/'current.log').write_bytes(current.stdout+b'\n'+current.stderr)
 cases=read_result('current.xml');bad=sum(c.find('failure') is not None or c.find('error') is not None for c in cases);skips=sum(c.find('skipped') is not None for c in cases)
 runner_result=runner_component(work,services['runner']['Image'])
 result={'candidate_image':new['Id'],'previous_image':OLD_IMAGE,'worker_sha256':EXPECTED['worker.py'],'previous_worker_sha256':OLD_SHA,
  'old_counterexamples':5,'linux_heartbeat_tests':len(cases),'failures':bad,'skipped':skips,'all_passed':current.returncode==0 and len(cases)==22 and bad==0 and skips==0 and runner_result['runner_test_passed'],
  **runner_result,
  'image_configuration_unchanged':True,'only_worker_module_layer_added':True,'runtime_pytest_added':False,
  'local_cutoff_seconds':45,'server_lease_seconds':90,'nas_services_reconfigured':False,'duration_seconds':time.monotonic()-started}
 (work/'validation.json').write_text(json.dumps(result,indent=2))
finally:
 ids=call(prefix+['ps','-aq','--filter','label=io.leroy.operator-test=worker-cadence-20261014']).decode().split()
 for identity in ids:
  item=json.loads(call(prefix+['inspect',identity]))[0]
  assert item['Image']==new['Id'] and item['Config']['Labels']['io.leroy.operator-test']=='worker-cadence-20261014'
  if item['State']['Running']:call(prefix+['stop','--time','10',identity],timeout=20)
  if subprocess.run(prefix+['inspect',identity],capture_output=True).returncode==0:call(prefix+['rm',identity])
 assert not call(prefix+['ps','-aq','--filter','label=io.leroy.operator-test=worker-cadence-20261014']).strip()
 (work/'cleanup.json').write_text(json.dumps({'test_containers_removed':True,'running_services_changed':False}))
for name,before in services.items():
 after=inspect('leroy-nas-parity-'+name+'-1')
 assert before['Id']==after['Id'] and before['State']['Pid']==after['State']['Pid'] and before['Image']==after['Image']
print(json.dumps({'validation':result,'test_containers_removed':True}))
assert result['all_passed'],'Candidate tests failed; retain private evidence'
'''


RESUME_COMPONENT_SCOPE = RUNNER_COMPONENT + r'''
import hashlib,json,os,pathlib,subprocess,tarfile,xml.etree.ElementTree as ET
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
def call(args,timeout=30):
 r=subprocess.run(args,capture_output=True,timeout=timeout);assert r.returncode==0,'Scoped component qualification failed; output withheld';return r.stdout
def inspect(name):return json.loads(call(['docker','inspect',name]))[0]
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
services={name:inspect('leroy-nas-parity-'+name+'-1') for name in ('controller','postgres','runner','docker')}
prefix=['docker','exec',services['docker']['Id'],'docker']
assert call(prefix+['inspect','jenkins-parity','--format','{{.State.Running}}']).decode().strip()=='false'
assert not call(prefix+['ps','-q','--filter','label=io.leroy.runner=runner-nas-parity']).strip()
for c in json.loads(call(['docker','inspect','paperless','sonarr','radarr','sabnzbd','plex','yt-downloader-service','mail-ingest-service'])):
 assert c['State']['Running'] and c['State'].get('Health',{}).get('Status') in (None,'healthy')
work=root/'worker-lease-cadence-qualification-20261014';source=root/'worker-lease-cadence-20261014.tar'
assert hashlib.sha256(source.read_bytes()).hexdigest()==ARCHIVE_SHA
initial=json.loads((work/'validation.json').read_text());assert not initial['all_passed'] and initial['failures']==1 and initial['linux_heartbeat_tests']==23
assert initial['worker_sha256']==EXPECTED['worker.py'] and initial['previous_image']==OLD_IMAGE
mixed=ET.parse(work/'current.xml').findall('.//testcase')
excluded=[c for c in mixed if c.attrib['name']=='test_docker_operations_have_a_timeout']
assert len(excluded)==1 and excluded[0].find('failure') is not None
cases=[c for c in mixed if c not in excluded]
assert len(cases)==22 and all(not any(c.find(k) is not None for k in ('failure','error','skipped')) for c in cases)
old_cases=ET.parse(work/'old.xml').findall('.//testcase')
assert len(old_cases)==5 and all(c.find('failure') is not None for c in old_cases)
old=json.loads(call(prefix+['image','inspect',OLD_IMAGE]))[0];new=json.loads(call(prefix+['image','inspect',initial['candidate_image']]))[0]
assert old['Config']==new['Config'] and old['RootFS']['Layers']==new['RootFS']['Layers'][:-1]
assert not (work/'validation-initial-mixed.json').exists()
(work/'validation-initial-mixed.json').write_bytes((work/'validation.json').read_bytes())
runner_result=runner_component(work,services['runner']['Image'])
result={**initial,**runner_result,'linux_heartbeat_tests':22,'failures':0,'skipped':0,
 'all_passed':runner_result['runner_test_passed'],'component_scope_repaired':True,
 'initial_mixed_failure_preserved':True,'worker_cases_taken_from_unmodified_original_xml':True,
 'original_mixed_worker_xml_sha256':hashlib.sha256((work/'current.xml').read_bytes()).hexdigest()}
(work/'validation.json').write_text(json.dumps(result,indent=2))
for name,before in services.items():
 after=inspect('leroy-nas-parity-'+name+'-1');assert before['Id']==after['Id'] and before['Image']==after['Image'] and before['State']['Pid']==after['State']['Pid']
assert not call(prefix+['ps','-aq','--filter','label=io.leroy.operator-test=worker-cadence-20261014']).strip()
print(json.dumps({'validation':result,'test_containers_removed':True}))
assert result['all_passed'],'Runner component test failed; retain all evidence'
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume-component-scope', action='store_true', help='Preserve the mixed-image failure and test its Runner case in the actual Runner image')
    args = parser.parse_args()
    require_restored_windows()
    idle()
    assert not vm.state()['State']['Running']
    proof = json.loads((FOLLOWUP / 'reconcile8g-window-plan-20261014/worker-cadence-source-proof.json').read_text())
    source = ROOT / 'src/leroy/worker.py'
    assert vm.digest(source) == proof['worker_sha256'] and proof['previous_worker_sha256'] == OLD_SHA
    assert proof['only_renewal_wait_expression_changed'] and proof['local_non_postgres_passed'] == 250
    FOLDER.mkdir(exist_ok=True)
    marker = FOLDER / 'qualification-start.json'
    assert marker.exists() == args.resume_component_scope, 'Retain an uncertain qualification before explicitly resuming'
    files = {'worker.py': source,
             'worker-before.py': FOLLOWUP / 'reconcile8g-window-plan-20261014/worker-before-cadence.py',
             'test_heartbeat.py': ROOT / 'tests/test_heartbeat.py',
             'pytest-runtime.zip': FOLLOWUP / 'controller-reconcile-locks-20261014/pytest-runtime.zip'}
    expected = {name: vm.digest(path) for name, path in files.items()}
    archive = FOLDER / 'worker-lease-cadence-20261014.tar'
    if args.resume_component_scope:
        retained = json.loads(marker.read_text())
        assert retained['expected'] == expected and not (FOLDER / 'qualification-proof.json').exists()
        guard = retained['production_guard_before']
    else:
        guard = begin(FOLDER, 'worker-cadence-qualification')
        with tarfile.open(archive, 'w') as bundle:
            for name, path in files.items():
                bundle.add(path, arcname=name)
        marker.write_text(json.dumps({'production_guard_before': guard, 'expected': expected}) + '\n')
        upload_file(archive, '/volume1/docker/leroy-nas-parity/' + archive.name, vm.CREDENTIALS)
    payload = RESUME_COMPONENT_SCOPE if args.resume_component_scope else PROGRAM
    program = ('OLD_IMAGE=' + repr(OLD_IMAGE) + '\nOLD_SHA=' + repr(OLD_SHA) + '\nEXPECTED=' + repr(expected) +
               '\nARCHIVE_SHA=' + repr(hashlib.sha256(archive.read_bytes()).hexdigest()) + '\n' + payload)
    (FOLDER / ('qualification-scope-repair.py' if args.resume_component_scope else 'qualification-program.py')).write_text(program)
    value = json.loads(vm.remote(program, sudo=True, timeout=600))
    (FOLDER / 'qualification-proof.json').write_text(json.dumps(value, indent=2) + '\n')
    finish(FOLDER, 'worker-cadence-qualification', guard)
    print(json.dumps(value))


if __name__ == '__main__':
    main()
