"""Qualify a controller-only logging layer against a full, unread OS output pipe."""

import argparse
import json
import tarfile

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, upload_file

BASE = ROOT / 'test-results/nas-parity/followup'
FOLDER = BASE / 'console-queue-20261017'
OLD = 'sha256:ffaa70367cd503b316c714859df6fefa1275344fee1fcfe5cc183b8878c477aa'

PROGRAM = r'''
import hashlib,json,os,pathlib,re,subprocess,tarfile,xml.etree.ElementTree as ET
owner=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (owner/'.leroy-owned').is_file()
def call(args,timeout=30,**kw):
 r=subprocess.run(args,capture_output=True,timeout=timeout,**kw)
 assert r.returncode==0,'Owned console qualification failed; inspect protected evidence'
 return r.stdout
def inspect(name):return json.loads(call(['docker','inspect',name]))[0]
controller=inspect('leroy-nas-parity-controller-1');assert controller['Image']==OLD
before={n:inspect('leroy-nas-parity-'+n+'-1') for n in ('controller','postgres','runner','docker')}
assert all(c['State']['Running'] for c in before.values())
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
prefix=['docker','exec',before['docker']['Id'],'docker']
assert call(prefix+['inspect','jenkins-parity','--format','{{.State.Running}}']).strip()==b'false'
assert not call(prefix+['ps','-q','--filter','label=io.leroy.runner=runner-nas-parity']).strip()
for c in json.loads(call(['docker','inspect','paperless','sonarr','radarr','sabnzbd','plex','yt-downloader-service','mail-ingest-service'])):
 assert c['State']['Running'] and c['State'].get('Health',{}).get('Status') in (None,'healthy')
source=owner/'console-queue-inputs-20261017.tar';assert hashlib.sha256(source.read_bytes()).hexdigest()==ARCHIVE_SHA
work=owner/'console-queue-qualification-20261017'
if VERIFY_EXISTING:
 assert work.is_dir() and json.loads((work/'qualification.json').read_text())['all_passed'] is True
else:
 assert not work.exists();work.mkdir(mode=0o700)
with tarfile.open(source) as bundle:
 assert {m.name for m in bundle.getmembers()}==set(EXPECTED) and len(bundle.getmembers())==len(EXPECTED)
 for m in bundle.getmembers():
  assert m.isfile() and pathlib.PurePosixPath(m.name).name==m.name and m.size<32*1024**2
  data=bundle.extractfile(m).read();assert hashlib.sha256(data).hexdigest()==EXPECTED[m.name]
  (work/m.name).write_bytes(data);(work/m.name).chmod(0o644)
package=call(['docker','exec',controller['Id'],'python','-c',
 "import pathlib,leroy;print(pathlib.Path(leroy.__file__).parent)"]).decode().strip()
assert re.fullmatch('/usr/local/lib/python3[.][0-9]+/site-packages/leroy',package)
tag='leroy-controller:nas-console-queue-20261017';base='leroy-controller:before-console-queue-20261017'
if not VERIFY_EXISTING:
 for name in (tag,base):assert subprocess.run(['docker','image','inspect',name],capture_output=True).returncode!=0
 call(['docker','tag',OLD,base])
dockerfile='FROM '+base+'\nCOPY console_logging.py server.py '+package+'/\nCMD ["sh","-c","alembic upgrade head && exec python -m leroy.server"]\n'
(work/'Dockerfile').write_text(dockerfile);(work/'Dockerfile').chmod(0o600)
if not VERIFY_EXISTING:call(['docker','build','--network=none','--pull=false','-t',tag,str(work)],timeout=120)
old=json.loads(call(['docker','image','inspect',OLD]))[0]
new=json.loads(call(['docker','image','inspect',tag]))[0]
assert new['RootFS']['Layers'][:-1]==old['RootFS']['Layers']
assert {k:v for k,v in new['Config'].items() if k!='Cmd'}=={k:v for k,v in old['Config'].items() if k!='Cmd'}
results=work/('verification-results' if VERIFY_EXISTING else 'results')
results.mkdir(mode=0o750);os.chown(results,10001,10001);work.chmod(0o755)
name='leroy-console-queue-qualification-20261017'
args=['docker','run','--rm','--name',name,'--label','io.leroy.operator-test=console-queue-20261017',
 '--user','10001:10001','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
 '--memory','256m','--memory-swap','256m','--cpus','1','--pids-limit','128',
 '--tmpfs','/tmp:rw,nosuid,size=64m,mode=1777','--mount','type=bind,src='+str(work)+',dst=/operator,readonly',
 '--mount','type=bind,src='+str(results)+',dst=/results','-e','PYTHONPATH=/operator/pytest-runtime.zip',
 '-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTEST_DISABLE_PLUGIN_AUTOLOAD=1','--entrypoint','python',new['Id'],
 '-B','-m','pytest','/operator/test_console_logging.py','-q','-p','no:cacheprovider','--junitxml=/results/tests.xml']
test=subprocess.run(args,capture_output=True,timeout=180)
(work/'tests.log').write_bytes(test.stdout+b'\n'+test.stderr)
cases=ET.fromstring((results/'tests.xml').read_bytes()).findall('.//testcase')
bad=sum(any(c.find(k) is not None for k in ('failure','error','skipped')) for c in cases)
proof={'previous_image':OLD,'candidate_image':new['Id'],'native_linux_tests':len(cases),'failures_or_skips':bad,
 'all_passed':test.returncode==0 and len(cases)==6 and bad==0,'source_sha256':EXPECTED,
 'rootfs_only_logging_modules_added':True,'image_configuration_changed_fields':['Cmd'],
 'real_unread_os_pipe_tested':True,'api_and_shutdown_responsive_under_backpressure':test.returncode==0,
 'controller_deployed':False,'worker_changed':False,'graphato_sources_tests_or_fixture_limits_changed':False,
 'vm_started':False,'seven_services_paused':False,'production_modified':False}
(work/('verification.json' if VERIFY_EXISTING else 'qualification.json')).write_text(json.dumps(proof,indent=2)+'\n')
for n,prior in before.items():
 after=inspect('leroy-nas-parity-'+n+'-1')
 assert all(after[k]==prior[k] for k in ('Id','Image','Config','HostConfig'))
 assert sorted(after['Mounts'],key=lambda m:m['Destination'])==sorted(prior['Mounts'],key=lambda m:m['Destination'])
 assert after['State']['Pid']==prior['State']['Pid']
proof['main_service_configuration_and_processes_unchanged']=True
(work/('verification.json' if VERIFY_EXISTING else 'qualification.json')).write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof));assert proof['all_passed'],'Do not deploy an unqualified logging layer'
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-existing', action='store_true', help='Explicitly recheck the retained, already tested image; no rebuild')
    args = parser.parse_args()
    if args.verify_existing:
        assert FOLDER.is_dir() and not (FOLDER / 'verification-program.py').exists()
    else:
        assert not FOLDER.exists(), 'Retain an uncertain qualification rather than repeat it'
    idle()
    assert not vm.state()['State']['Running']
    FOLDER.mkdir(exist_ok=args.verify_existing)
    before = begin(FOLDER, 'console-queue-qualification')
    inputs = {'console_logging.py': ROOT / 'src/leroy/console_logging.py',
              'server.py': ROOT / 'src/leroy/server.py',
              'test_console_logging.py': ROOT / 'tests/test_console_logging.py',
              'pytest-runtime.zip': BASE / 'controller-reconcile-locks-20261014/pytest-runtime.zip'}
    archive = FOLDER / 'inputs.tar'
    if not args.verify_existing:
        with tarfile.open(archive, 'w') as bundle:
            for name, path in inputs.items():
                bundle.add(path, arcname=name)
    expected = {name: vm.digest(path) for name, path in inputs.items()}
    upload_file(archive, '/volume1/docker/leroy-nas-parity/console-queue-inputs-20261017.tar', vm.CREDENTIALS)
    program = ('VERIFY_EXISTING=' + repr(args.verify_existing) + '\nOLD=' + repr(OLD)
               + '\nARCHIVE_SHA=' + repr(vm.digest(archive)) + '\nEXPECTED=' + repr(expected) + '\n' + PROGRAM)
    (FOLDER / ('verification-program.py' if args.verify_existing else 'program.py')).write_text(program)
    proof = json.loads(vm.remote(program, sudo=True, timeout=360))
    (FOLDER / 'qualification-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    finish(FOLDER, 'console-queue-qualification', before)
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
