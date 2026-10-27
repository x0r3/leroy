"""Bounded synthetic memory capacity probe, normally with NAS applications active.

This is supporting evidence only. It never dispatches Graphato CI, changes its
fixtures, pauses NAS services, or qualifies a complete release. A separate
explicitly approved window may provide the paused-service context. Each allocation
is admitted conservatively; insufficient reserve is an inconclusive refusal.
The guest agent frees its allocations after loss of its operator connection.
"""

import argparse
import json
import time

import nas_release_vm as vm
from diagnose_nas_release_group import collect_memory_evidence
from nas_followup_support import production_jobs
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_vm_cache import collect_guest_guard, start_guest_guard
from nas_vm_memory_pressure import apply_outer_memory_pressure
from nas_vm_memory_trace import start_trace
from nas_vm_page_reporting import apply_guest_page_reporting

AGENT = r'''
import json,mmap,os,pathlib,resource,socket,threading,time
assert os.geteuid()==0 and pathlib.Path('/var/lib/leroy-vm/ready').is_file()
resource.setrlimit(resource.RLIMIT_AS,(7680*1024**2,7680*1024**2))
resource.setrlimit(resource.RLIMIT_CPU,(120,120))
timer=threading.Timer(900,lambda:os._exit(124));timer.daemon=True;timer.start()
root=pathlib.Path('/var/tmp/leroy-capacity-probe');parts=[];allocated=0;initial_total=None
def memory():
 return {s.split(':')[0]:int(s.split()[1]) for s in pathlib.Path('/proc/meminfo').read_text().splitlines() if s.startswith(('MemTotal:','MemAvailable:','MemFree:','Cached:','AnonPages:','SwapTotal:'))}
def report(kind,**extra):
 global initial_total
 m=memory()
 if initial_total is None:initial_total=m['MemTotal']
 assert m['MemTotal']==initial_total and m['SwapTotal']==0
 value={'at':time.time(),'kind':kind,'allocated_mib':allocated,'guest_memory_kib':m,**extra}
 (root/'latest.json').write_text(json.dumps(value));print(json.dumps(value),flush=True);return value
try:
 with socket.socket(socket.AF_UNIX) as server:
  server.bind(str(root/'control.sock'));os.chmod(root/'control.sock',0o600);server.listen(1);server.settimeout(70)
  report('ready')
  while True:
   with server.accept()[0] as connection:
    connection.settimeout(5);data=connection.makefile('rb').readline(1025)
    assert len(data)<=1024;action=json.loads(data)
    if action=={'action':'status'}:
     value=report('held');connection.sendall((json.dumps(value)+'\n').encode());continue
    if action=={'action':'stop'}:
     intact=all(block[offset]==1 for block in parts for offset in range(0,len(block),1024**2))
     for block in parts:block.close()
     parts=[];allocated=0
     value=report('stopped',sampled_pages_intact=intact);connection.sendall((json.dumps(value)+'\n').encode());break
    assert set(action)=={'action','mib'} and action['action']=='allocate'
    size=action['mib'];assert type(size) is int and size==512 and allocated+size<=6144
    if memory()['MemAvailable']<(size+512)*1024:
     value=report('guest_admission_declined')
    else:
     block=mmap.mmap(-1,size*1024**2,flags=mmap.MAP_PRIVATE|mmap.MAP_ANONYMOUS,prot=mmap.PROT_READ|mmap.PROT_WRITE)
     block.madvise(mmap.MADV_NOHUGEPAGE)
     for offset in range(0,len(block),4096):block[offset]=1
     parts.append(block);allocated+=size;value=report('allocated')
    connection.sendall((json.dumps(value)+'\n').encode())
finally:
 for block in parts:block.close()
 timer.cancel();report('agent_finished')
'''

START = r'''
import hashlib,json,os,pathlib,subprocess,time
assert os.geteuid()==0 and pathlib.Path('/var/lib/leroy-vm/ready').is_file()
root=pathlib.Path('/var/tmp/leroy-capacity-probe');assert not root.exists();root.mkdir(mode=0o700)
path=root/'agent.py';path.write_text(AGENT);path.chmod(0o700)
with (root/'agent.jsonl').open('xb') as log:
 process=subprocess.Popen(['/usr/bin/python3','-B',str(path)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
for _ in range(100):
 if (root/'control.sock').exists():break
 assert process.poll() is None,'Capacity agent failed; retain its own diagnostic log'
 time.sleep(.1)
assert (root/'control.sock').exists()
print(json.dumps({'pid':process.pid,'program_sha256':hashlib.sha256(AGENT.encode()).hexdigest(),'idle_timeout_seconds':70,'hard_timeout_seconds':900,'source_or_tests_changed':False}))
'''

CONTROL = r'''
import json,os,pathlib,socket
assert os.geteuid()==0 and pathlib.Path('/var/lib/leroy-vm/ready').is_file()
with socket.socket(socket.AF_UNIX) as stream:
 stream.settimeout(60);stream.connect('/var/tmp/leroy-capacity-probe/control.sock')
 stream.sendall((json.dumps(ACTION)+'\n').encode());stream.shutdown(socket.SHUT_WR)
 value=json.loads(stream.makefile('rb').readline(8192));print(json.dumps(value))
'''

HOST = r'''
import json,pathlib,time
print(json.dumps({'at':time.time(),'memory_kib':{s.split(':')[0]:int(s.split()[1]) for s in pathlib.Path('/proc/meminfo').read_text().splitlines() if s.startswith(('MemAvailable:','SwapFree:'))}}))
'''


def control(action):
    return json.loads(vm.guest('sudo python3 -B -', 'ACTION=' + repr(action) + '\n' + CONTROL, timeout=85))


def admit_host(memory):
    # Budget the next 512 MiB wholly against swap, plus 256 MiB headroom.
    # Refusal does not prove the original job could never run.
    return (memory['SwapFree'] >= (vm.MIN_HOST_SWAP_MB + 512 + 256) * 1024 and
            memory['MemAvailable'] >= (vm.MIN_HOST_AVAILABLE_MB + 128) * 1024)


def resource_context(window, round_name=None):
    if window is not None:
        if window == 'resource-window-night-20261014':
            from run_nas_night_window import require_approval
        else:
            from run_nas_capacity_window import require_approval
        require_approval()
    program = 'WINDOW=' + repr(window) + '\nROUND=' + repr(round_name) + '\n' + r'''
import json,pathlib,runpy,subprocess
names=['paperless','sonarr','radarr','sabnzbd','plex','yt-downloader-service','mail-ingest-service']
rows=json.loads(subprocess.check_output(['docker','inspect',*names],text=True,timeout=20))
if WINDOW is not None:
 root=pathlib.Path('/volume1/docker/leroy-nas-parity')/WINDOW
 guard=runpy.run_path(str(root/'guard.py'));state=guard['read']()
 assert state['phase']=='paused' and ROUND in state['comparison_rounds']
 if WINDOW=='resource-window-capacity-order0-20261014':
  assert state['maximum_window_seconds']==3600 and state['comparison_rounds']==['capacity-window-order0-20261014']
 else:
  assert WINDOW==guard['NIGHT_WINDOW'] and state['comparison_rounds']==guard['NIGHT_ROUNDS']
  assert state['deadline']==state['absolute_deadline_epoch']
 for row in state['containers']:assert not guard['reviewed'](row)['State']['Running']
else:
 assert all(c['State']['Running'] and c['State'].get('Health',{}).get('Status') in (None,'healthy') for c in rows)
print(json.dumps({'services_paused':WINDOW is not None,'resource_window':WINDOW,
 'services':[{'name':c['Name'].lstrip('/'),'id':c['Id'],'running':c['State']['Running'],'health':c['State'].get('Health',{}).get('Status')} for c in rows]}))
'''
    return json.loads(vm.remote(program, sudo=True, timeout=45))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--round', required=True)
    parser.add_argument('--page-reporting-order', choices=(0, 4), type=int, default=0)
    parser.add_argument('--target-hold-seconds', choices=(20, 60), type=int, default=20)
    parser.add_argument('--resource-window', choices=('resource-window-capacity-order0-20261014', 'resource-window-night-20261014'))
    parser.add_argument('--resource-profile', choices=('nas-8g-ssd-soft-ram-3584', 'nas-8g-ssd-soft-ram-3840',
                                                     'nas-8g-ssd-soft-ram-4096'), default='nas-8g-ssd-soft-ram-3584')
    parser.add_argument('--early-memory-pressure', action='store_true')
    args = parser.parse_args()
    context = resource_context(args.resource_window, args.round)
    if args.resource_window == 'resource-window-capacity-order0-20261014':
        assert args.round == 'capacity-window-order0-20261014' and args.page_reporting_order == 0
        assert args.resource_profile == 'nas-8g-ssd-soft-ram-3584' and not args.early_memory_pressure
    if args.resource_window == 'resource-window-night-20261014':
        assert args.round == 'night-capacity' + args.resource_profile.rsplit('-', 1)[1] + '-20261014'
        assert args.page_reporting_order == 0 and args.early_memory_pressure and args.target_hold_seconds == 60
    vm.configure(args.round, args.resource_profile)
    folder = vm.ROOT / 'test-results/nas-parity/followup' / args.round
    assert not folder.exists(), 'Retain the previous probe; no implicit repeat'
    folder.mkdir()
    idle()
    guard = begin(folder, 'synthetic-capacity')
    production = production_jobs()
    marker = {'synthetic_only': True, 'original_ci_dispatched': False, 'nas_services_paused': context['services_paused'],
              'resource_context': context, 'target_hold_seconds': args.target_hold_seconds,
              'page_reporting_order': args.page_reporting_order, 'guest_mib': 8192,
              'memory_high_mib': int(args.resource_profile.rsplit('-', 1)[1]), 'target_anonymous_mib': 6144,
              'early_memory_pressure': args.early_memory_pressure,
              'original_fixture_limit_emulated': False, 'application_source_or_tests_changed': False,
              'admission_headroom_mib': 256, 'complete_release_acceptance': False, 'production_ready': False}
    (folder / 'prepared.json').write_text(json.dumps(marker, indent=2) + '\n')
    trace_started = cache_started = agent_started = False
    phases = []
    reason = 'not_completed'
    try:
        vm.start('leroy', postgres_init=True, memory_pressure_folder=folder if args.early_memory_pressure else None)
        apply_guest_page_reporting(folder, 'leroy', order=args.page_reporting_order)
        apply_outer_memory_pressure(folder, 'leroy')
        start_guest_guard(folder, 'leroy')
        cache_started = True
        start_trace(folder, 'leroy')
        trace_started = True
        agent = json.loads(vm.guest('sudo python3 -B -', 'AGENT=' + repr(AGENT) + '\n' + START, timeout=45))
        (folder / 'agent-identity.json').write_text(json.dumps(agent, indent=2) + '\n')
        agent_started = True
        for step in range(12):
            current = production_jobs(history=False)
            if current['active_builds'] or current['jobs'] != production['jobs']:
                reason = 'production_build_changed'
                break
            host = json.loads(vm.remote(HOST, timeout=20))
            if not admit_host(host['memory_kib']):
                reason = 'conservative_host_admission_declined'
                phases.append({'at': host['at'], 'host': host, 'kind': reason})
                break
            value = control({'action': 'allocate', 'mib': 512})
            phases.append({'host_before': host, **value})
            (folder / 'phases.json').write_text(json.dumps(phases, indent=2) + '\n')
            print(json.dumps({'step': step + 1, 'allocated_mib': value['allocated_mib'], 'kind': value['kind']}), flush=True)
            if value['kind'] != 'allocated':
                reason = value['kind']
                break
            if step == 11:
                for _ in range(args.target_hold_seconds // 20):
                    time.sleep(20)
                    current = production_jobs(history=False)
                    assert not current['active_builds'] and current['jobs'] == production['jobs']
                    phases.append(control({'action': 'status'}))
            else:
                time.sleep(20)
        else:
            reason = 'synthetic_target_held'
        stopped = control({'action': 'stop'})
        agent_started = False
        phases.append(stopped)
        assert stopped['sampled_pages_intact']
        time.sleep(20)
    except Exception as error:
        reason = 'operator_or_resource_error:' + type(error).__name__
        (folder / 'operation-error.json').write_text(json.dumps({'type': type(error).__name__}) + '\n')
        raise
    finally:
        if agent_started:
            try:
                phases.append(control({'action': 'stop'}))
            except Exception as error:
                phases.append({'agent_cleanup_error': type(error).__name__, 'idle_timeout_seconds': 70})
        (folder / 'phases.json').write_text(json.dumps(phases, indent=2) + '\n')
        if trace_started:
            collect_memory_evidence(folder, 'leroy')
        state = vm.state()
        if state and state['State']['Running']:
            assert state['Config']['Labels']['io.leroy.comparison'] == args.round
            if cache_started:
                try:
                    collect_guest_guard(folder, 'leroy')
                finally:
                    vm.stop()
            else:
                vm.stop()
        after = production_jobs()
        remaining = vm.state()
        final = {**marker, 'reason': reason, 'peak_allocated_mib': max((v.get('allocated_mib', 0) for v in phases), default=0),
                 'vm_running': bool(remaining and remaining['State']['Running']), 'production_before': production, 'production_after': after}
        (folder / 'final-state.json').write_text(json.dumps(final, indent=2) + '\n')
        finish(folder, 'synthetic-capacity', guard)
        print(json.dumps({k: v for k, v in final.items() if k not in {'production_before', 'production_after'}}), flush=True)


if __name__ == '__main__':
    main()
