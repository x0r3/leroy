"""Check private SSD-backed guest RAM inside the unchanged 6-GiB no-swap limit."""

import json
import subprocess
import time

import nas_release_vm as vm
from nas_followup_support import production_jobs
from nas_vm_memory_trace import start_trace

TARGET_MIB = 5888
AGENT = r'''
import json,mmap,os,pathlib,resource,socket,struct,threading,time
assert os.geteuid()==0
resource.setrlimit(resource.RLIMIT_AS,(7*1024**3,7*1024**3))
resource.setrlimit(resource.RLIMIT_CPU,(120,120))
timer=threading.Timer(1200,lambda:os._exit(124));timer.daemon=True;timer.start()
root=pathlib.Path('/probe');parts=[];allocated=0
def intact(stride):
 return all(struct.unpack_from('<Q',block,offset)[0]==(index<<32)+offset//4096+1
            for index,block in enumerate(parts) for offset in range(0,len(block),stride))
def value(kind,**extra):return {'at_epoch':time.time(),'kind':kind,'allocated_mib':allocated,**extra}
try:
 with socket.socket(socket.AF_UNIX) as server:
  server.bind(str(root/'control.sock'));os.chmod(root/'control.sock',0o600);server.listen(1);server.settimeout(120)
  while True:
   with server.accept()[0] as stream:
    stream.settimeout(5);request=json.loads(stream.makefile('rb').readline(1025))
    if request=={'action':'status'}:
     result=value('held')
    elif request=={'action':'stop'}:
     good=intact(4096)
     for block in parts:block.close()
     parts=[];allocated=0;result=value('stopped',all_page_markers_intact=good)
    else:
     assert set(request)=={'action','mib'} and request['action']=='allocate'
     size=request['mib'];assert size in (256,512) and allocated+size<=5888
     available=next(int(line.split()[1]) for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
     if available<(size+128)*1024:result=value('guest_admission_declined')
     else:
      block=mmap.mmap(-1,size*1024**2,flags=mmap.MAP_PRIVATE|mmap.MAP_ANONYMOUS,prot=mmap.PROT_READ|mmap.PROT_WRITE)
      block.madvise(mmap.MADV_NOHUGEPAGE);index=len(parts)
      for offset in range(0,len(block),4096):struct.pack_into('<Q',block,offset,(index<<32)+offset//4096+1)
      parts.append(block);allocated+=size;result=value('allocated')
    print(json.dumps(result),flush=True);stream.sendall((json.dumps(result)+'\n').encode())
    if result['kind']=='stopped':break
finally:
 for block in parts:block.close()
 timer.cancel()
'''
START = r'''
import hashlib,json,os,pathlib,subprocess,time
assert os.geteuid()==0 and pathlib.Path('/var/lib/leroy-vm/ready').is_file()
root=pathlib.Path('/var/tmp/leroy-file-memory-capacity');assert not root.exists();root.mkdir(mode=0o700)
path=root/'agent.py';path.write_text(AGENT);path.chmod(0o700)
assert json.loads(subprocess.check_output(['docker','image','inspect',IMAGE]))[0]['Id']==IMAGE
args=['docker','run','--rm','--pull','never','--init','--name',NAME,'--label','io.leroy.file-memory-probe=true',
 '--network','none','--user','0:0','--cap-drop','ALL','--security-opt','no-new-privileges:true','--read-only',
 '--memory','6g','--memory-swap','6g','--cpus','2','--pids-limit','64','--tmpfs','/tmp:size=16m',
 '--mount','type=bind,source='+str(root)+',target=/probe','--entrypoint','python3',IMAGE,'-B','/probe/agent.py']
with (root/'agent.jsonl').open('xb') as log:
 process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
for _ in range(300):
 if (root/'control.sock').exists():break
 assert process.poll() is None,'Synthetic probe failed; diagnostic log retained'
 time.sleep(.1)
assert (root/'control.sock').exists()
info=json.loads(subprocess.check_output(['docker','inspect',NAME]))[0];assert info['State']['Running'] and info['Image']==IMAGE
cfg=info['HostConfig'];assert cfg['Memory']==6*1024**3 and cfg['MemorySwap']==6*1024**3 and cfg['NanoCpus']==2*10**9
relative=next(line[3:] for line in pathlib.Path('/proc',str(info['State']['Pid']),'cgroup').read_text().splitlines() if line.startswith('0::'))
cg=pathlib.Path('/sys/fs/cgroup'+relative);assert cg.resolve()==cg and cg.name in (info['Id'],'docker-'+info['Id']+'.scope')
assert int((cg/'memory.swap.max').read_text())==0
print(json.dumps({'container_id':info['Id'],'image':IMAGE,'memory_bytes':cfg['Memory'],
 'memory_and_swap_bytes':cfg['MemorySwap'],'nano_cpus':cfg['NanoCpus'],'cgroup_swap_max':0,
 'program_sha256':hashlib.sha256(AGENT.encode()).hexdigest(),'hard_timeout_seconds':1200,'idle_timeout_seconds':120}))
'''
CONTROL = r'''
import json,pathlib,socket
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
with socket.socket(socket.AF_UNIX) as stream:
 stream.settimeout(360);stream.connect('/var/tmp/leroy-file-memory-capacity/control.sock')
 stream.sendall((json.dumps(ACTION)+'\n').encode());stream.shutdown(socket.SHUT_WR)
 value=json.loads(stream.makefile('rb').readline(8192));print(json.dumps(value))
'''


def control(action):
    return json.loads(vm.guest('sudo python3 -B -', 'ACTION=' + repr(action) + '\n' + CONTROL, timeout=420))


def admission_read(folder, engine, operation, read, until):
    """Retry only unavailable reads, within one fixed shared admission budget."""
    while True:
        remaining = until - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Capacity admission state remains unknown; do not allocate memory')
        try:
            return read(min(15, remaining))
        except (vm.SSHTransportUnavailable, subprocess.TimeoutExpired) as error:
            with (folder / (engine + '-capacity-read-unknown.jsonl')).open('a') as stream:
                stream.write(json.dumps({'at_epoch': time.time(), 'operation': operation,
                                         'error_type': type(error).__name__, 'outcome_unknown': True,
                                         'allocation_repeated': False}) + '\n')
        time.sleep(min(5, max(0, until - time.monotonic())))


def qualify(folder, engine, *, local_admission=False):
    if local_admission:
        from nas_vm_capacity_local import qualify as qualify_on_nas

        return qualify_on_nas(folder, engine, guest_agent=AGENT, start_program=START, control_program=CONTROL)
    assert vm.RESOURCE_PROFILE in vm.FILE_MEMORY_PROFILES and vm.ROUND == folder.name
    marker = folder / (engine + '-file-memory-capacity.json')
    assert not marker.exists(), 'Retain the first qualification; never restart its allocations'
    if not (folder / (engine + '-memory-trace.json')).exists():
        start_trace(folder, engine)
    scenario = json.loads((vm.ROOT / 'test-results/nas-parity/followup/candidates/graphato' / vm.COMMIT /
                           'scenarios/root-private-existing-host/scenario.json').read_text())
    image = scenario['baseline_release']['runtimeImageId']
    name = 'leroy-file-memory-capacity-' + engine
    before = production_jobs()
    assert not before['active_builds']
    started = json.loads(vm.guest('sudo python3 -B -', 'IMAGE=' + repr(image) + '\nNAME=' + repr(name) +
                                 '\nAGENT=' + repr(AGENT) + '\n' + START, timeout=60))
    (folder / (engine + '-file-memory-capacity-started.json')).write_text(json.dumps(started, indent=2) + '\n')
    phases, stopped = [], False
    try:
        for amount in [512] * 11 + [256]:
            until = time.monotonic() + 60
            current = admission_read(folder, engine, 'production_jobs',
                                     lambda timeout: production_jobs(history=False, timeout=timeout), until)
            assert not current['active_builds'] and current['jobs'] == before['jobs']
            memory = admission_read(folder, engine, 'host_memory', lambda timeout: json.loads(vm.remote(
                "import json,pathlib\nprint(json.dumps({l.split(':')[0]:int(l.split()[1]) for l in pathlib.Path('/proc/meminfo').read_text().splitlines() if l.startswith(('MemAvailable:','SwapFree:'))}))",
                timeout=timeout)), until)
            assert memory['MemAvailable'] >= (vm.MIN_HOST_AVAILABLE_MB + 128) * 1024
            assert memory['SwapFree'] >= (vm.MIN_HOST_SWAP_MB + amount + 256) * 1024
            value = control({'action': 'allocate', 'mib': amount})
            phases.append({**value, 'host_before_kib': memory})
            with (folder / (engine + '-file-memory-capacity-phases.jsonl')).open('a') as stream:
                stream.write(json.dumps(phases[-1]) + '\n')
            assert value['kind'] == 'allocated', 'Conservative admission declined; do not dispatch original CI'
            print(json.dumps({'engine': engine, 'synthetic_allocated_mib': value['allocated_mib']}), flush=True)
            time.sleep(5)
        assert phases[-1]['allocated_mib'] == TARGET_MIB
        for _ in range(3):
            time.sleep(20)
            current = admission_read(folder, engine, 'production_jobs_while_held',
                                     lambda timeout: production_jobs(history=False, timeout=timeout),
                                     time.monotonic() + 60)
            assert not current['active_builds'] and current['jobs'] == before['jobs']
            value = control({'action': 'status'})
            assert value['kind'] == 'held' and value['allocated_mib'] == TARGET_MIB
            phases.append(value)
        value = control({'action': 'stop'})
        stopped = True
        assert value['all_page_markers_intact']
        phases.append(value)
        proof = {'qualified_synthetic_capacity': True, 'allocated_mib': TARGET_MIB, 'hold_seconds': 60,
                 'all_page_markers_intact': True, 'original_fixture_limits_emulated': True, 'limits': started,
                 'original_ci_dispatched': False, 'application_source_or_tests_changed': False,
                 'host_swap_changed': False, 'full_release_acceptance_complete': False, 'phases': phases}
        marker.write_text(json.dumps(proof, indent=2) + '\n')
    finally:
        if not stopped:
            try:
                control({'action': 'stop'})
            except Exception as error:
                (folder / (engine + '-file-memory-capacity-cleanup-error.json')).write_text(json.dumps({'type': type(error).__name__}) + '\n')
    # The ephemeral container is removed; baseline release and receipts are untouched.
    for _ in range(30):
        active = vm.guest('sudo python3 -B -', 'import json,subprocess\nprint(json.dumps(subprocess.check_output(' +
                          repr(['docker', 'ps', '-q', '--filter', 'name=^/' + name + '$']) + ').decode().strip()))', timeout=30)
        if not json.loads(active):
            return proof
        time.sleep(1)
    raise RuntimeError('Synthetic container remains active; do not dispatch original CI')
