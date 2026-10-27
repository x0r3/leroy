"""Qualify the missing startup lease cadence fix in the actual NAS Runner image."""

import json
import tarfile

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, upload_file

BASE = ROOT / 'test-results/nas-parity/followup'
FOLDER = BASE / 'runner-cadence-completion-20261015'
OLD_IMAGE = 'sha256:620623e9be9a3bfdbc521c066de591ae973badeb7e4e05429493bef18dad6416'

PROGRAM = r'''
import ast,hashlib,json,os,pathlib,subprocess,tarfile,xml.etree.ElementTree as ET
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
def call(args,timeout=30,**kw):
 r=subprocess.run(args,capture_output=True,timeout=timeout,**kw)
 assert r.returncode==0,'Owned Runner qualification failed; output withheld'
 return r.stdout
def inspect(name):return json.loads(call(['docker','inspect',name]))[0]
services={n:inspect('leroy-nas-parity-'+n+'-1') for n in ('controller','postgres','runner','docker')}
assert all(c['State']['Running'] and c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' for c in services.values())
assert services['runner']['Image']==OLD_IMAGE
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
prefix=['docker','exec',services['docker']['Id'],'docker']
assert call(prefix+['inspect','jenkins-parity','--format','{{.State.Running}}']).strip()==b'false'
assert not call(prefix+['ps','-aq','--filter','label=io.leroy.runner=runner-nas-parity']).strip()
for c in json.loads(call(['docker','inspect','paperless','sonarr','radarr','sabnzbd','plex','yt-downloader-service','mail-ingest-service'])):
 assert c['State']['Running'] and c['State'].get('Health',{}).get('Status') in (None,'healthy')
work=root/'runner-cadence-qualification-20261015';assert not work.exists();work.mkdir(mode=0o700)
source=root/'runner-cadence-completion-20261015.tar';assert hashlib.sha256(source.read_bytes()).hexdigest()==ARCHIVE_SHA
with tarfile.open(source) as bundle:
 members=bundle.getmembers();assert len(members)==len(EXPECTED) and {m.name for m in members}==set(EXPECTED)
 for m in members:
  assert m.isfile() and m.name==pathlib.PurePosixPath(m.name).name and m.size<24*1024**2
  data=bundle.extractfile(m).read();assert hashlib.sha256(data).hexdigest()==EXPECTED[m.name]
  p=work/m.name;p.write_bytes(data);p.chmod(0o644)
work.chmod(0o755);results=work/'results';results.mkdir(mode=0o750);os.chown(results,10001,10001)
old_source=(work/'worker-before.py').read_text();new_source=(work/'worker.py').read_text()
def nodes(s):return {getattr(n,'name',str(i)):ast.dump(n,include_attributes=False) for i,n in enumerate(ast.parse(s).body)}
before=nodes(old_source);after=nodes(new_source);assert before.keys()==after.keys()
assert [k for k in before if before[k]!=after[k]]==['maintain_lease']
assert hashlib.sha256(old_source.encode()).hexdigest()==SOURCE_PROOF['sha256']
base='leroy-runner:nas-before-cadence-20261015';tag='leroy-runner:nas-cadence-20261015'
for name in (base,tag):assert subprocess.run(['docker','image','inspect',name],capture_output=True).returncode!=0
call(['docker','tag',OLD_IMAGE,base])
dockerfile='FROM '+base+'\nCOPY worker.py '+SOURCE_PROOF['path']+'\n'
call(['docker','build','--network=none','--pull=false','-t',tag,'-f','-',str(work)],input=dockerfile.encode(),timeout=120)
old=json.loads(call(['docker','image','inspect',OLD_IMAGE]))[0];new=json.loads(call(['docker','image','inspect',tag]))[0]
assert old['Config']==new['Config'] and new['RootFS']['Layers'][:-1]==old['RootFS']['Layers']
common=['docker','run','--rm','--init','--user','10001:10001','--network','none','--read-only','--cap-drop','ALL',
 '--security-opt','no-new-privileges:true','--memory','256m','--memory-swap','256m','--cpus','1','--pids-limit','128',
 '--tmpfs','/tmp:rw,nosuid,size=64m,mode=1777','--mount','type=bind,src='+str(work)+',dst=/operator,readonly',
 '--mount','type=bind,src='+str(results)+',dst=/results','-e','PYTHONPATH=/operator/pytest-runtime.zip',
 '-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTEST_DISABLE_PLUGIN_AUTOLOAD=1',
 '--label','io.leroy.operator-test=runner-cadence-20261015','--entrypoint','python']
def run(image,name,selection):
 r=subprocess.run(common+['--name','leroy-runner-cadence-'+name+'-20261015',image,'-m','pytest',
 '/operator/test_heartbeat.py','-k',selection,'-q','-p','no:cacheprovider','--junitxml=/results/'+name+'.xml'],capture_output=True,timeout=180)
 (work/(name+'.log')).write_bytes(r.stdout+b'\n'+r.stderr)
 cases=ET.parse(results/(name+'.xml')).findall('.//testcase');return r.returncode,cases
try:
 code,cases=run(OLD_IMAGE,'baseline','successful_request_time_counts_towards_renewal_cadence')
 assert code==1 and len(cases)==5 and all(c.find('failure') is not None for c in cases)
 code,cases=run(new['Id'],'current','')
 bad=sum(any(c.find(k) is not None for k in ('failure','error','skipped')) for c in cases)
 proof={'candidate_image':new['Id'],'previous_image':OLD_IMAGE,'worker_sha256':EXPECTED['worker.py'],
 'old_counterexamples':5,'linux_runner_tests':len(cases),'failures_or_skips':bad,
 'all_passed':code==0 and len(cases)==23 and bad==0,'only_maintain_lease_function_changed':True,
 'image_configuration_unchanged':True,'base_layers_retained':True,'local_cutoff_seconds':45,'server_lease_seconds':90,
 'runtime_pytest_added':False,'production_modified':False}
 (work/'validation.json').write_text(json.dumps(proof,indent=2)+'\n')
finally:
 for cid in call(['docker','ps','-aq','--filter','label=io.leroy.operator-test=runner-cadence-20261015']).decode().split():
  c=inspect(cid);assert c['Image'] in {OLD_IMAGE,new['Id']} and c['Config']['Labels']['io.leroy.operator-test']=='runner-cadence-20261015'
  call(['docker','rm','-f',cid])
for name,before in services.items():
 after=inspect('leroy-nas-parity-'+name+'-1');assert (before['Id'],before['Image'],before['State']['Pid'])==(after['Id'],after['Image'],after['State']['Pid'])
print(json.dumps(proof));assert proof['all_passed'],'Runner tests failed; retain evidence'
'''


def main():
    idle()
    assert not (FOLDER / 'qualification-start.json').exists()
    files = {'worker.py': FOLDER / 'worker.py', 'worker-before.py': FOLDER / 'worker-before.py',
             'test_heartbeat.py': ROOT / 'tests/test_heartbeat.py',
             'pytest-runtime.zip': BASE / 'controller-reconcile-locks-20261014/pytest-runtime.zip'}
    expected = {name: vm.digest(path) for name, path in files.items()}
    archive = FOLDER / 'qualification-inputs.tar'
    with tarfile.open(archive, 'w') as bundle:
        for name, path in files.items():
            bundle.add(path, arcname=name)
    before = begin(FOLDER, 'runner-cadence-qualification')
    (FOLDER / 'qualification-start.json').write_text(json.dumps({'production_guard_before': before, 'expected': expected}) + '\n')
    upload_file(archive, '/volume1/docker/leroy-nas-parity/runner-cadence-completion-20261015.tar', vm.CREDENTIALS)
    values = {'OLD_IMAGE': OLD_IMAGE, 'EXPECTED': expected, 'ARCHIVE_SHA': vm.digest(archive),
              'SOURCE_PROOF': json.loads((FOLDER / 'source-proof.json').read_text())}
    program = ''.join(k + '=' + repr(v) + '\n' for k, v in values.items()) + PROGRAM
    (FOLDER / 'qualification-program.py').write_text(program)
    proof = json.loads(vm.remote(program, sudo=True, timeout=600))
    (FOLDER / 'qualification-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    finish(FOLDER, 'runner-cadence-qualification', before)
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
