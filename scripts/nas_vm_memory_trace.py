"""Bounded NAS-local memory observations, independent of CI and Windows SSH."""

import base64
import gzip
import hashlib
import json

import nas_release_vm as vm

GUEST = r'''
import json,pathlib,time
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
def fields(path):
 return {s[0].rstrip(':'):int(s[1]) for line in pathlib.Path(path).read_text().splitlines() if len(s:=line.split())>=2 and s[1].isdigit()}
mem=fields('/proc/meminfo');stat=fields('/proc/vmstat')
print(json.dumps({'at':time.time(),'memory_kib':{k:mem[k] for k in ('MemTotal','MemAvailable','MemFree','Cached','Dirty','Writeback','SwapTotal','SwapFree','Slab','SReclaimable','PageTables','AnonPages')},
 'vmstat':{k:v for k,v in stat.items() if k.startswith(('balloon_','pgscan_','pgsteal_','allocstall_')) or k in ('oom_kill','pgmajfault')},
 'pressure':{n:pathlib.Path('/proc/pressure',n).read_text().strip() for n in ('memory','io')}}))
'''

PROGRAM = r'''
import json,os,pathlib,signal,subprocess,time
assert os.geteuid()==0
os.nice(15)
root=pathlib.Path(DIRECTORY);identity=json.loads((root/'identity.json').read_text())
info=json.loads(subprocess.check_output(['docker','inspect',CONTAINER],text=True,timeout=15))[0]
assert info['Id']==identity['container_id'] and info['State']['Pid']==identity['vm_pid'] and info['State']['Running']
process=pathlib.Path('/proc',str(identity['vm_pid']))
def ticks(p):return p.joinpath('stat').read_text().rpartition(') ')[2].split()[19]
assert ticks(process)==identity['vm_process_start_ticks']
def fields(path):
 return {s[0].rstrip(':'):int(s[1]) for line in pathlib.Path(path).read_text().splitlines() if len(s:=line.split())>=2 and s[1].isdigit()}
def cgpath(pid):
 relative=next(x[3:] for x in pathlib.Path('/proc',str(pid),'cgroup').read_text().splitlines() if x.startswith('0::'))
 p=pathlib.Path('/sys/fs/cgroup'+relative)
 assert p.resolve()==p and p.is_relative_to('/sys/fs/cgroup') and p!=pathlib.Path('/sys/fs/cgroup')
 return p
own=cgpath(identity['vm_pid'])
assert own.name in (info['Id'],'docker-'+info['Id']+'.scope')
def cgroup(p):
 result={}
 for name in ('memory.current','memory.swap.current','memory.max','memory.high','memory.swap.max'):
  result[name]=p.joinpath(name).read_text().strip()
 for name in ('memory.stat','memory.events','cpu.stat','io.stat'):
  result[name]=p.joinpath(name).read_text().strip()
 result['memory.pressure']=p.joinpath('memory.pressure').read_text().strip()
 return result
def host():
 m=fields('/proc/meminfo');s=fields('/proc/vmstat')
 return {'at':time.time(),'memory_kib':{k:m[k] for k in ('MemTotal','MemAvailable','MemFree','Cached','SwapTotal','SwapFree','SReclaimable','AnonPages','Slab','PageTables')},
 'vmstat':{k:s[k] for k in ('pswpin','pswpout','oom_kill','pgmajfault')},
 'pressure':{n:pathlib.Path('/proc/pressure',n).read_text().strip() for n in ('memory','io','cpu')}}
ids=subprocess.check_output(['docker','ps','-aq'],text=True,timeout=15).split()
containers=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True,timeout=20)) if ids else []
tracked=[]
for c in containers:
 if c['State']['Running']:
  try:tracked.append((c['Name'].lstrip('/'),cgpath(c['State']['Pid'])))
  except (OSError,StopIteration):pass
stopped=False
def stop(*_):
 global stopped
 stopped=True
signal.signal(signal.SIGTERM,stop)
log=root/'samples.jsonl';started=time.monotonic();count=0
with log.open('x',buffering=1) as stream:
 os.chmod(log,0o600)
 while not stopped and time.monotonic()-started<4*3600 and stream.tell()<24*1024**2:
  begin=time.monotonic();row={'at':time.time(),'sequence':count,'host_before':host()}
  try:
   assert ticks(process)==identity['vm_process_start_ticks']
   row['owned_vm_cgroup']=cgroup(own)
   qemus=[]
   for pid in own.joinpath('cgroup.procs').read_text().split():
    p=pathlib.Path('/proc',pid)
    try:
     if p.joinpath('comm').read_text().startswith('qemu-system'):
      status=fields(p/'status')
      qemus.append({'pid':int(pid),'memory_kib':{'Rss':status['VmRSS'],'Swap':status['VmSwap']},
       'source':'proc_status','smaps_page_walk_performed':False})
    except (OSError,ProcessLookupError):pass
   row['qemu']=qemus
   args=['nsenter','-t',str(identity['vm_pid']),'-n','ssh','-T','-i',REMOTE+'/admin-key','-p','12225',
    '-o','UserKnownHostsFile='+REMOTE+'/known_hosts','-o','HostKeyAlias=graphato-parity','-o','StrictHostKeyChecking=yes',
    '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=3',
    '-o','ControlMaster=auto','-o','ControlPersist=600','-o','ControlPath='+REMOTE+'/.admin-'+ENGINE+'.sock',
    'leroy-admin@127.0.0.1','python3 -B -']
   try:
    r=subprocess.run(args,input=GUEST,text=True,capture_output=True,timeout=6)
    if r.returncode:row['guest_error']='nonzero_exit'
    else:row['guest']=json.loads(r.stdout)
   except (subprocess.TimeoutExpired,ValueError):row['guest_error']='timeout_or_invalid_json'
   if count%3==0:
    rows={}
    for name,p in tracked:
     try:rows[name]={'memory_bytes':int(p.joinpath('memory.current').read_text()),'swap_bytes':int(p.joinpath('memory.swap.current').read_text())}
     except OSError:rows[name]={'unavailable':True}
    row['nas_containers']=rows
  except (OSError,AssertionError,ProcessLookupError):
   row['owned_vm_process_ended']=True;stopped=True
  row['host_after']=host();row['sample_seconds']=time.monotonic()-begin
  stream.write(json.dumps(row,separators=(',',':'))+'\n');count+=1
  remaining=10-(time.monotonic()-begin)
  while remaining>0 and not stopped:
   time.sleep(min(remaining,0.5));remaining=10-(time.monotonic()-begin)
 (root/'finished.json').write_text(json.dumps({'samples':count,'duration_seconds':time.monotonic()-started,'observer_stopped':True}))
'''


def start_trace(folder, engine):
    assert engine in {'jenkins', 'leroy'} and vm.ROUND == folder.name
    source = ('CONTAINER=' + repr(vm.CONTAINER) + '\nREMOTE=' + repr(vm.REMOTE) +
              '\nENGINE=' + repr(engine) + '\nGUEST=' + repr(GUEST) + '\n')
    directory = vm.REMOTE + '/memory-traces/' + vm.ROUND + '/' + engine
    source += 'DIRECTORY=' + repr(directory) + '\n' + PROGRAM
    sha = hashlib.sha256(source.encode()).hexdigest()
    program = ('DIRECTORY=' + repr(directory) + '\nSOURCE=' + repr(source) + '\nEXPECTED=' + repr(sha) +
               '\nROUND=' + repr(vm.ROUND) + '\nENGINE=' + repr(engine) + '\nCOMMIT=' + repr(vm.COMMIT) + '\n' + r'''
import hashlib,json,os,pathlib,subprocess,time
assert os.geteuid()==0
info=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-release-target-vm'],text=True,timeout=15))[0]
assert info['State']['Running'] and all(info['Config']['Labels'][k]==v for k,v in
 [('io.leroy.comparison',ROUND),('io.leroy.engine',ENGINE),('io.leroy.nas-release-target',COMMIT)])
root=pathlib.Path(DIRECTORY);assert root.resolve()==root and not root.is_symlink() and not root.exists()
root.mkdir(parents=True,mode=0o700);root.chmod(0o700)
program=root/'observer.py';program.write_text(SOURCE);program.chmod(0o700)
assert hashlib.sha256(program.read_bytes()).hexdigest()==EXPECTED
def ticks(pid):return pathlib.Path('/proc',str(pid),'stat').read_text().rpartition(') ')[2].split()[19]
identity={'container_id':info['Id'],'vm_pid':info['State']['Pid'],'vm_process_start_ticks':ticks(info['State']['Pid']),
 'observer_source_sha256':EXPECTED,'guest_and_host_configuration_changed':False,'application_source_or_tests_changed':False}
(root/'identity.json').write_text(json.dumps(identity));(root/'identity.json').chmod(0o600)
with (root/'observer-output.log').open('xb') as stream:
 p=subprocess.Popen(['/usr/bin/python3','-B',str(program)],stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
os.chmod(root/'observer-output.log',0o600)
identity.update(observer_pid=p.pid,observer_start_ticks=ticks(p.pid),directory=DIRECTORY)
(root/'identity.json').write_text(json.dumps(identity));time.sleep(1)
assert p.poll() is None,'Observer failed before CI; diagnostic output remains private'
print(json.dumps(identity))
''')
    proof = json.loads(vm.remote(program, sudo=True, timeout=45))
    (folder / (engine + '-memory-trace.json')).write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def collect_trace(folder, engine):
    marker = folder / (engine + '-memory-trace.json')
    proof = json.loads(marker.read_text())
    code = 'EXPECTED=' + repr(proof) + '\n' + r'''
import base64,gzip,hashlib,json,os,pathlib,signal,time
assert os.geteuid()==0
root=pathlib.Path(EXPECTED['directory']);assert root.resolve()==root and not root.is_symlink()
assert json.loads((root/'identity.json').read_text())==EXPECTED
assert hashlib.sha256((root/'observer.py').read_bytes()).hexdigest()==EXPECTED['observer_source_sha256']
p=pathlib.Path('/proc',str(EXPECTED['observer_pid']))
if p.exists() and p.joinpath('stat').read_text().rpartition(') ')[2].split()[0]!='Z':
 assert p.joinpath('stat').read_text().rpartition(') ')[2].split()[19]==EXPECTED['observer_start_ticks']
 assert p.joinpath('cmdline').read_bytes().split(b'\0')[:-1]==[b'/usr/bin/python3',b'-B',str(root/'observer.py').encode()]
 os.kill(EXPECTED['observer_pid'],signal.SIGTERM)
 for _ in range(120):
  if (root/'finished.json').exists():break
  time.sleep(0.5)
assert (root/'finished.json').exists(),'Observer has not flushed; retain and collect later'
log=root/'samples.jsonl';assert log.stat().st_size<=25*1024**2 and not log.is_symlink()
data=log.read_bytes();print(json.dumps({'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
 'finished':json.loads((root/'finished.json').read_text()),'gzip_base64':base64.b64encode(gzip.compress(data)).decode()}))
'''
    value = json.loads(vm.remote(code, sudo=True, timeout=60))
    data = gzip.decompress(base64.b64decode(value.pop('gzip_base64')))
    assert len(data) == value['bytes'] and hashlib.sha256(data).hexdigest() == value['sha256']
    (folder / (engine + '-memory-samples.jsonl')).write_bytes(data)
    (folder / (engine + '-memory-trace-complete.json')).write_text(json.dumps(value, indent=2) + '\n')
    return value


def summarize(rows):
    """Separate aligned samples, missing guest data, and host-wide swap pressure."""
    if not rows:
        raise ValueError('No memory observations retained')
    paired = [r for r in rows if 'guest' in r and
              r['host_before']['at'] <= r['guest']['at'] <= r['host_after']['at'] and
              r['host_after']['at'] - r['host_before']['at'] <= 10]
    own = [r['owned_vm_cgroup'] for r in rows if 'owned_vm_cgroup' in r]
    host = [r[phase]['memory_kib'] for r in rows for phase in ('host_before', 'host_after')]
    qemu = [q['memory_kib'] for r in rows for q in r.get('qemu', [])]
    return {
        'samples': len(rows), 'aligned_guest_host_samples': len(paired),
        'guest_observation_errors': sum('guest_error' in r for r in rows),
        'guest_unaligned_or_missing_samples': len(rows) - len(paired),
        'minimum_host_available_kib': min(r['MemAvailable'] for r in host),
        'minimum_host_swap_free_kib': min(r['SwapFree'] for r in host),
        'peak_owned_vm_memory_bytes': max((int(r['memory.current']) for r in own), default=None),
        'peak_owned_vm_swap_bytes': max((int(r['memory.swap.current']) for r in own), default=None),
        'peak_qemu_rss_kib': max((r.get('Rss', 0) for r in qemu), default=None),
        'peak_qemu_swap_kib': max((r.get('Swap', 0) for r in qemu), default=None),
        'minimum_aligned_guest_available_kib': min((r['guest']['memory_kib']['MemAvailable'] for r in paired), default=None),
        'minimum_aligned_guest_free_kib': min((r['guest']['memory_kib']['MemFree'] for r in paired), default=None),
        'guest_oom_kill_counters': sorted({r['guest']['vmstat']['oom_kill'] for r in paired}),
        'physical_nas_oom_kill_counters': sorted({r['host_after']['vmstat']['oom_kill'] for r in rows}),
        'memory_trace_alone_proves_test_completion': False,
        'equal_background_load_proven': False,
    }
