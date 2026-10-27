"""Optional clean-cache reclamation inside the owned test guest, never on the NAS."""

import hashlib
import json
import re

import nas_release_vm as vm


def host_needs_cache_relief(memory):
    return memory['SwapFree'] < (vm.MIN_HOST_SWAP_MB + 2048) * 1024


GUEST_PROGRAM = r'''
import json,os,pathlib,subprocess,time
assert os.geteuid()==0
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip()=='kvm'
def memory():
 return {line.split(':')[0]:int(line.split()[1]) for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:','MemAvailable:','MemFree:','Cached:','Dirty:','Writeback:'))}
before=memory()
performed=before['MemAvailable']>=1024*1024 and before['Cached']>=768*1024
if performed:
 # Value 1 releases clean file cache. It neither changes dirty data nor RAM limits.
 pathlib.Path('/proc/sys/vm/drop_caches').write_text('1\n')
 time.sleep(2)
print(json.dumps({'guest_before_kib':before,'guest_after_kib':memory(),'clean_cache_relief_performed':performed,'host_kernel_modified':False,'application_source_changed':False,'application_tests_changed':False,'fixture_resource_limits_changed':False}))
'''


def relieve_cache():
    info = vm.state()
    assert info['State']['Running'] and info['Config']['Labels']['io.leroy.comparison'] == vm.ROUND
    value = json.loads(vm.guest('sudo python3 -B -', GUEST_PROGRAM, timeout=45))
    value['engine'] = info['Config']['Labels']['io.leroy.engine']
    return value


def guard_program():
    """A guest-local policy remains available when NAS/SSH observations stall."""
    return ('ACTION=' + repr(GUEST_PROGRAM) + '\n' + r'''
import contextlib,io,json,time
while True:
 output=io.StringIO()
 try:
  with contextlib.redirect_stdout(output):exec(ACTION,{})
  value=json.loads(output.getvalue());value['guest_time']=time.time()
 except Exception as error:
  print(json.dumps({'guest_time':time.time(),'policy_error':type(error).__name__}),flush=True)
  raise SystemExit(1)
 print(json.dumps(value),flush=True)
 time.sleep(30)
''')


def guard_root(engine):
    assert engine in {'leroy', 'jenkins'} and re.fullmatch('[a-z0-9-]{1,64}', vm.ROUND or '')
    return '/var/lib/leroy-vm/cache-guards/' + vm.ROUND + '/' + engine


def start_guest_guard(folder, engine):
    info = vm.state()
    assert info['State']['Running']
    assert info['Config']['Labels']['io.leroy.comparison'] == vm.ROUND
    assert info['Config']['Labels']['io.leroy.engine'] == engine
    source = guard_program()
    code = ('DIRECTORY=' + repr(guard_root(engine)) + '\nPROGRAM=' + repr(source) + '\n' + r'''
import hashlib,json,os,pathlib,subprocess
assert os.geteuid()==0 and pathlib.Path('/var/lib/leroy-vm/ready').is_file()
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip()=='kvm'
root=pathlib.Path(DIRECTORY);assert root.resolve()==root and not root.is_symlink()
root.mkdir(mode=0o700,parents=True,exist_ok=True);root.chmod(0o700)
program=root/'policy.py';identity=root/'identity.json';log=root/'observations.jsonl'
sha=hashlib.sha256(PROGRAM.encode()).hexdigest()
assert not any(path.is_symlink() for path in (program,identity,log))
if identity.exists():
 value=json.loads(identity.read_text());assert value['program_sha256']==sha
 assert hashlib.sha256(program.read_bytes()).hexdigest()==sha
 pid=value['pid'];process=pathlib.Path('/proc',str(pid))
 assert process.stat().st_uid==0
 assert process.joinpath('cmdline').read_bytes().split(b'\0')[:-1]==[b'/usr/bin/python3',b'-B',str(program).encode()]
 assert process.joinpath('stat').read_text().split()[21]==value['process_start_ticks']
else:
 assert not program.exists() and not log.exists()
 program.write_text(PROGRAM);program.chmod(0o700)
 with log.open('xb') as output:
  process=subprocess.Popen(['/usr/bin/python3','-B',str(program)],stdin=subprocess.DEVNULL,
                           stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
 log.chmod(0o600)
 value={'pid':process.pid,'program_sha256':sha,
        'process_start_ticks':pathlib.Path('/proc',str(process.pid),'stat').read_text().split()[21]}
 identity.write_text(json.dumps(value));identity.chmod(0o600)
print(json.dumps({**value,'guest_directory':str(root),'interval_seconds':30,
 'minimum_guest_available_mb':1024,'minimum_guest_cached_mb':768,
 'host_kernel_modified':False,'application_tests_changed':False,'fixture_resource_limits_changed':False}))
''')
    proof = json.loads(vm.guest('sudo python3 -B -', code, timeout=60))
    assert proof['program_sha256'] == hashlib.sha256(source.encode()).hexdigest()
    (folder / (engine + '-guest-cache-guard.json')).write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def collect_guest_guard(folder, engine):
    """Stop only the verified own policy process once its original CI has ended."""
    info = vm.state()
    assert info['Config']['Labels']['io.leroy.comparison'] == vm.ROUND
    assert info['Config']['Labels']['io.leroy.engine'] == engine
    if not info['State']['Running']:
        proof = {'available': False, 'reason': 'owned_vm_already_stopped',
                 'engine': engine, 'round': vm.ROUND, 'original_ci_restarted': False}
        path = folder / (engine + '-guest-cache-observations-unavailable.json')
        if not path.exists():
            path.write_text(json.dumps(proof, indent=2) + '\n')
        return proof
    code = ('DIRECTORY=' + repr(guard_root(engine)) + '\n' + r'''
import hashlib,json,os,pathlib,signal,time
assert os.geteuid()==0
root=pathlib.Path(DIRECTORY);assert root.resolve()==root and not root.is_symlink()
value=json.loads((root/'identity.json').read_text());program=root/'policy.py'
assert hashlib.sha256(program.read_bytes()).hexdigest()==value['program_sha256']
process=pathlib.Path('/proc',str(value['pid']))
running=process.exists()
if running:
 assert process.stat().st_uid==0
 assert process.joinpath('cmdline').read_bytes().split(b'\0')[:-1]==[b'/usr/bin/python3',b'-B',str(program).encode()]
 assert process.joinpath('stat').read_text().split()[21]==value['process_start_ticks']
 os.kill(value['pid'],signal.SIGTERM);time.sleep(1)
log=root/'observations.jsonl';assert log.is_file() and not log.is_symlink() and log.stat().st_size<=4*1024**2
text=log.read_text();rows=[json.loads(line) for line in text.splitlines()]
print(json.dumps({'identity':value,'was_running':running,'observations':rows,
 'log_sha256':hashlib.sha256(text.encode()).hexdigest(),'host_kernel_modified':False}))
''')
    proof = json.loads(vm.guest('sudo python3 -B -', code, timeout=60))
    (folder / (engine + '-guest-cache-observations.json')).write_text(json.dumps(proof, indent=2) + '\n')
    return proof
