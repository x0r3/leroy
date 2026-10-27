"""Add bounded passive HTTP evidence to an unchanged original dev-environments run.

This observer has measurable overhead and captures HTTP metadata, not browser DOM.
The application source, test command, original five-second assertions and fixture
limits stay unchanged. Run under both engines with identical observer settings.
"""

import base64
import hashlib
import json
import sys

import compare_nas_full_release as release
import diagnose_nas_release_group as diagnostic
import nas_release_vm as vm
from nas_ssh import ROOT


def main():
    assert '--group' in sys.argv and sys.argv[sys.argv.index('--group')+1] == 'dev-environments'
    folder = (ROOT / sys.argv[sys.argv.index('--folder')+1]).resolve()
    assert folder.is_relative_to(ROOT / 'test-results/nas-parity/followup')
    name = folder.name
    remote = '/var/lib/leroy-diagnostics/'+name
    restore, stop = release.restore, vm.stop
    active = (folder/'http-observer-started.json').exists() and not (folder/'http-observer').exists()

    def observed_restore(*args):
        nonlocal active
        restore(*args)
        assert not active
        sources = {'observe.py':ROOT/'scripts/diagnostics/nas-passive-http.py',
                   'watch.py':ROOT/'scripts/diagnostics/nas-group-http-watch.py'}
        encoded = {n:base64.b64encode(p.read_bytes()).decode() for n,p in sources.items()}
        code = 'WORK='+repr(remote)+'\nFILES='+repr(encoded)+'\n'+r'''
import base64,json,os,pathlib,subprocess
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip()=='kvm'
parent=pathlib.Path('/var/lib/leroy-diagnostics');parent.mkdir(mode=0o700,exist_ok=True)
assert parent.resolve()==parent and parent.stat().st_uid==0
work=pathlib.Path(WORK);assert work.parent==parent and not work.exists()
work.mkdir(mode=0o700)
(work/'.leroy-owned').write_text('Unchanged dev-environments diagnostic observer\n')
(work/'runtime.txt').write_text('sha256:6251c60f499e41e706613f931bf281ce52312b957d5a6a123cf4e27dd3242585\n')
for name,value in FILES.items():
 p=work/name;p.write_bytes(base64.b64decode(value,validate=True));p.chmod(0o600)
with (work/'watch-console.log').open('xb') as out:
 process=subprocess.Popen(['python3','-B',str(work/'watch.py')],cwd=work,stdout=out,stderr=out,start_new_session=True)
(work/'watch-pid.json').write_text(json.dumps({'pid':process.pid}))
print(json.dumps({'watcher_started':True,'pid':process.pid,'browser_dom_observed':False,'observer_overhead_excluded':False}))
'''
        value = json.loads(vm.guest('sudo python3 -B -', code, timeout=45))
        value['source_sha256'] = {n:hashlib.sha256(p.read_bytes()).hexdigest() for n,p in sources.items()}
        (folder/'http-observer-started.json').write_text(json.dumps(value,indent=2)+'\n')
        active = True

    def observed_stop():
        nonlocal active
        if active and vm.state()['State']['Running']:
            code = 'WORK='+repr(remote)+'\n'+r'''
import base64,json,pathlib,time
work=pathlib.Path(WORK);assert work.parent==pathlib.Path('/var/lib/leroy-diagnostics')
assert (work/'.leroy-owned').read_text()=='Unchanged dev-environments diagnostic observer\n'
(work/'stop.flag').write_text('CI terminal; stop only the owned observers\n')
deadline=time.monotonic()+45
while not (work/'finished.json').is_file() and time.monotonic()<deadline:time.sleep(0.5)
assert (work/'finished.json').is_file(),'Retain an incomplete observer shutdown'
files={}
for pattern in ('finished.json','events.jsonl','proxy-errors.jsonl','server-*/http-metadata.jsonl','watch-console.log'):
 for p in work.glob(pattern):
  assert p.resolve().is_relative_to(work) and not p.is_symlink()
  assert p.stat().st_size<8*1024**2
  files[p.relative_to(work).as_posix()]=base64.b64encode(p.read_bytes()).decode()
print(json.dumps({'files':files}))
'''
            value = json.loads(vm.guest('sudo python3 -B -',code,timeout=70))
            destination = folder/'http-observer'
            destination.mkdir(exist_ok=False)
            for filename,payload in value['files'].items():
                path=(destination/filename).resolve()
                assert path.is_relative_to(destination.resolve())
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(base64.b64decode(payload,validate=True))
            active = False
        stop()

    release.restore, vm.stop = observed_restore, observed_stop
    diagnostic.main()


if __name__ == '__main__':
    main()
