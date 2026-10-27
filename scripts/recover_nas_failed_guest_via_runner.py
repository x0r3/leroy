"""Recover the exact failed W test guest through the existing isolated worker.

Use only after the original CI run is terminal. The already configured test
bootstrap credential never leaves the worker's private credential directory.
No NAS host command, new original build, or application patch is involved.
"""

import hashlib
import json
import time
from contextlib import closing

from compare_nas_antares import client
from nas_progress import publish
from nas_ssh import ROOT

RUN = 'f4af042f894b422bbeda50a8b07c8d98'
PIPELINE = 'nas-w-guest-recovery-20261017'
FOLDER = ROOT / 'test-results/nas-parity/followup/failed-w-guest-recovery-20261017'
COMMIT = '0ad540dd578033d45e4d0c25d89fbe57b32102a4'

GUEST = r'''
import json,os,pathlib,subprocess,time
assert os.geteuid()==0
boot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot==EXPECTED_BOOT,'Guest identity mismatch: no shutdown permitted'
assert pathlib.Path('/etc/hostname').read_text().strip()=='leroy-test-vm'
print(json.dumps({'event':'identity_verified','boot_id':boot,'original_ci_failed':True}),flush=True)
unit='leroy-failed-w-guest-poweroff-20261017'
load=subprocess.check_output(['systemctl','show',unit+'.timer','--property=LoadState','--value'],text=True,timeout=20).strip()
assert load=='not-found','Retain an already scheduled recovery rather than repeat it'
r=subprocess.run(['systemd-run','--unit='+unit,'--on-active=120s','--property=Type=oneshot',
 '/usr/bin/systemctl','--no-block','poweroff'],capture_output=True,text=True,timeout=30)
assert r.returncode==0,'Guest recovery timer not acknowledged'
print(json.dumps({'event':'owned_guest_poweroff_scheduled','after_seconds':120,'unit':unit,
 'boot_id':boot,'nas_host_modified':False}),flush=True)
p=pathlib.Path('/var/lib/graphato-host/postdeploy/results')/COMMIT/'quality'
receipt=p/'result.json'
if receipt.exists():
 assert receipt.stat().st_size<2*1024**2
 value=json.loads(receipt.read_text());assert value['commit']==COMMIT
 print(json.dumps({'event':'original_receipt_before_recovery','receipt':value}),flush=True)
for log in sorted(p.glob('*.log')):
 with log.open('rb') as stream:
  stream.seek(max(0,log.stat().st_size-16000));lines=stream.read().decode(errors='replace').splitlines()
 progress=[s[:300] for s in lines if any(k in s for k in ('Compiling ','Finished ','test result:',
   '[step start]','[step end]','ERROR:','error: could not compile','TimeoutExpired'))]
 print(json.dumps({'event':'original_log_progress','file':log.name,'bytes':log.stat().st_size,'tail':progress[-6:]}),flush=True)
'''

COMMAND = r'''
import hashlib,json,os,pathlib,subprocess,tempfile,time
out=pathlib.Path('recovery');out.mkdir()
assert os.environ.get('BOOTSTRAP_KEY') and pathlib.Path(os.environ['BOOTSTRAP_KEY']).is_file()
with tempfile.TemporaryDirectory(prefix='owned-guest-recovery-') as temporary:
 p=pathlib.Path(temporary);key=p/'key';key.write_bytes(pathlib.Path(os.environ['BOOTSTRAP_KEY']).read_bytes());key.chmod(0o600)
 public=subprocess.check_output(['ssh-keygen','-y','-f',str(key)],text=True,timeout=10)
 assert public.split()[:2]==EXPECTED_PUBLIC.split()[:2],'Unexpected test bootstrap credential'
 known=p/'known_hosts';known.write_text(KNOWN);known.chmod(0o600)
 args=['ssh','-F','/dev/null','-T','-i',str(key),'-p','12225','-o','HostKeyAlias=graphato-parity',
  '-o','UserKnownHostsFile='+str(known),'-o','StrictHostKeyChecking=yes','-o','IdentitiesOnly=yes',
  '-o','BatchMode=yes','-o','ConnectTimeout=60','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3',
  'root@10.232.98.11','python3 -B -']
 at=time.monotonic()
 try:
  r=subprocess.run(args,input=GUEST,text=True,capture_output=True,timeout=240)
  stdout,stderr,code=r.stdout,r.stderr,r.returncode
 except subprocess.TimeoutExpired as error:
  stdout=error.stdout or b'';stderr=error.stderr or b'';code=None
  if isinstance(stdout,bytes):stdout=stdout.decode(errors='replace')
  if isinstance(stderr,bytes):stderr=stderr.decode(errors='replace')
 events=[]
 for line in stdout.splitlines():
  try:events.append(json.loads(line))
  except ValueError:pass
 scheduled=any(e.get('event')=='owned_guest_poweroff_scheduled' and e.get('boot_id')==EXPECTED_BOOT for e in events)
 value={'seconds':round(time.monotonic()-at,3),'ssh_exit_code':code,'events':events,
  'transport_error':stderr[-1500:],'shutdown_acknowledged_for_exact_guest':scheduled,
  'original_graphato_ci_success':False,'application_sources_tests_changed':False,'nas_host_modified':False}
 (out/'guest-recovery.json').write_text(json.dumps(value,indent=2)+'\n')
 print(json.dumps({'shutdown_acknowledged_for_exact_guest':scheduled,'ssh_exit_code':code,'event_count':len(events)}),flush=True)
 assert scheduled,'No guest shutdown was acknowledged; retain the known diagnostic and independent NAS guard'
'''


def main():
    assert not FOLDER.exists(), 'Observe the retained recovery; never dispatch it twice'
    boot = json.loads((ROOT / 'test-results/nas-parity/followup/acceptance-20261017-w-rust-leroy/leroy-guest-page-reporting.json').read_text())['guest_boot_id']
    expected_public = (ROOT / '.local/nas-parity/config/test-secrets/bootstrap.pub').read_text()
    known = (ROOT / '.local/nas-full-release/0ad540dd5780/known_hosts').read_text()
    guest = 'EXPECTED_BOOT=' + repr(boot) + '\nCOMMIT=' + repr(COMMIT) + '\n' + GUEST
    command = ('EXPECTED_BOOT=' + repr(boot) + '\nEXPECTED_PUBLIC=' + repr(expected_public)
               + '\nKNOWN=' + repr(known) + '\nGUEST=' + repr(guest) + '\n' + COMMAND)
    spec = {'id': PIPELINE, 'name': 'Recover failed W test guest', 'group': 'Diagnostics',
            'profile': 'graphato', 'timeout': 600, 'enabled': False,
            'steps': [{'id': 'recover', 'name': 'Read failed guest evidence and schedule its poweroff',
                       'timeout': 400, 'command': ['python', '-u', '-c', command],
                       'secrets': ['graphato-bootstrap'], 'artifacts': ['recovery/guest-recovery.json']}]}
    with closing(client()) as api:
        r = api.get('/api/runs/' + RUN)
        r.raise_for_status()
        original = r.json()
        assert original['status'] == 'failed' and original['number'] == 186 and original['commit'] == COMMIT
        r = api.get('/api/pipelines')
        r.raise_for_status()
        assert PIPELINE not in {p['id'] for p in r.json()}
        FOLDER.mkdir()
        publish(FOLDER / 'intent.json', {'original_run_id': RUN, 'original_status': 'failed',
                 'guest_boot_id': boot, 'scope': 'only owned failed test guest; no NAS host shutdown',
                 'command_sha256': hashlib.sha256(command.encode()).hexdigest(), 'at_epoch': time.time()})
        r = api.put('/api/pipelines/' + PIPELINE, json=spec)
        r.raise_for_status()
        r = api.post('/api/pipelines/' + PIPELINE + '/runs', json={})
        r.raise_for_status()
        value = r.json()
        publish(FOLDER / 'start.json', value)
        print(json.dumps({'diagnostic_run_id': value['id'], 'pipeline': PIPELINE,
                          'original_ci_redispatched': False, 'guest_boot_id': boot}), flush=True)


if __name__ == '__main__':
    main()
