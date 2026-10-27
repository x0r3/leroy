"""One-shot NAS-local capacity driver; Windows only retrieves its evidence."""
import base64
import hashlib
import json
import subprocess
import time

import nas_release_vm as vm
from nas_followup_support import production_jobs, production_jobs_program
from nas_verified_container import HELPERS

RUNTIME_SECONDS = 1250


def approval_for(folder, engine):
    matches = []
    for path in folder.parent.glob('day-window-plan-*/approval.json'):
        value = json.loads(path.read_text())
        if value['comparison_rounds'] == [folder.name] and value['engine'] == engine:
            matches.append((path, value))
    assert len(matches) == 1, 'One exact source-bound window is required'
    path, value = matches[0]
    assert value['source_commit'] == vm.COMMIT and value['nas_local_capacity'] is True
    assert time.time() < value['absolute_deadline_epoch'] - 900
    return path, value


def validate_result(value, config, config_sha):
    from nas_capacity_agent import ALLOCATION_MIB, require_limits

    assert value['config_sha256'] == config_sha and value['driver_source_sha256'] == config['source_sha256']
    assert value['nas_local_admission'] is True and value['qualified_synthetic_capacity'] is True
    assert value['allocated_mib'] == 5888 and value['hold_seconds'] == 60 and value['all_page_markers_intact'] is True
    assert value['original_ci_dispatched'] is False and value['host_swap_changed'] is False
    require_limits(value['limits'], config['image'], hashlib.sha256(config['guest_agent'].encode()).hexdigest())
    phases = value['phases']
    assert len(phases) == len(ALLOCATION_MIB) + 4
    total = 0
    for phase, amount in zip(phases[:len(ALLOCATION_MIB)], ALLOCATION_MIB, strict=True):
        total += amount
        assert phase['kind'] == 'allocated' and phase['allocated_mib'] == total
        reserve = phase['host_before_kib']
        assert reserve['MemAvailable'] >= 256 * 1024 and reserve['SwapFree'] >= (2304 + amount + 256) * 1024
    assert all(p['kind'] == 'held' and p['allocated_mib'] == 5888 for p in phases[-4:-1])
    assert phases[-1]['kind'] == 'stopped' and phases[-1]['all_page_markers_intact'] is True
    resources = value['driver_resources']
    assert resources['memory.low'] == str(32 * 1024**2) and resources['memory.max'] == str(128 * 1024**2)
    assert resources['memory.min'] == resources['memory.swap.max'] == '0'
    assert resources['pids.max'] == '64'
    quota, period = map(int, resources['cpu.max'].split())
    assert quota * 2 == period


def qualify(folder, engine, *, guest_agent, start_program, control_program):
    assert vm.RESOURCE_PROFILE in vm.FILE_MEMORY_PROFILES and vm.ROUND == folder.name
    assert vm.MIN_HOST_AVAILABLE_MB == 128 and vm.MIN_HOST_SWAP_MB == 2304
    marker = folder / (engine + '-file-memory-capacity.json')
    intent = folder / (engine + '-nas-capacity-intent.json')
    assert not marker.exists() and not intent.exists(), 'Retrieve the retained agent; never start another allocation'
    approval_path, approval = approval_for(folder, engine)
    if not (folder / (engine + '-memory-trace.json')).exists():
        from nas_vm_memory_trace import start_trace

        start_trace(folder, engine)
    before = production_jobs()
    assert not before['active_builds']
    assert vm._GUEST_PIN is not None, 'Pin the ready guest before introducing capacity load'
    scenario = json.loads((vm.ROOT / 'test-results/nas-parity/followup/candidates/graphato' / vm.COMMIT /
                           'scenarios/root-private-existing-host/scenario.json').read_text())
    source = (vm.ROOT / 'scripts/nas_capacity_agent.py').read_bytes()
    tag = hashlib.sha256((folder.name + ':' + engine).encode()).hexdigest()[:12]
    directory = '/volume1/docker/leroy-nas-parity/capacity-agent-' + tag
    unit = 'leroy-capacity-' + tag + '.service'
    config = {'round': folder.name, 'engine': engine, 'commit': vm.COMMIT, 'window': approval['window'],
              'guard_sha256': approval['script_sha256']['scripts/nas_resource_window_guard.py'],
              'vm_pin': vm._GUEST_PIN, 'remote': vm.REMOTE, 'pin_verifier_source': HELPERS,
              'production_program': production_jobs_program(history=False), 'expected_production_jobs': before['jobs'],
              'source_sha256': hashlib.sha256(source).hexdigest(), 'image': scenario['baseline_release']['runtimeImageId'],
              'probe_name': 'leroy-file-memory-capacity-' + engine, 'guest_agent': guest_agent,
              'start_program': start_program, 'control_program': control_program}
    data = (json.dumps(config, separators=(',', ':')) + '\n').encode()
    config_sha = hashlib.sha256(data).hexdigest()
    retained = {'directory': directory, 'unit': unit, 'config_sha256': config_sha,
                'source_sha256': config['source_sha256'], 'round': folder.name, 'engine': engine,
                'at_epoch': time.time(), 'approval_sha256': vm.digest(approval_path)}
    intent.write_text(json.dumps(retained, indent=2) + '\n')
    (folder / (engine + '-nas-capacity-config.json')).write_bytes(data)
    launch = ('DIRECTORY=' + repr(directory) + '\nUNIT=' + repr(unit) + '\nCONFIG_SHA=' + repr(config_sha) +
              '\nSOURCE=' + repr(base64.b64encode(source).decode()) + '\nCONFIG=' + repr(base64.b64encode(data).decode()) + '\n' + r'''
import base64,hashlib,json,os,pathlib,subprocess,time
owner=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (owner/'.leroy-owned').is_file()
work=pathlib.Path(DIRECTORY);assert work.parent==owner and work.resolve()==work and not work.exists()
assert subprocess.check_output(['systemctl','show',UNIT,'-p','LoadState','--value'],text=True,timeout=15).strip()=='not-found'
assert pathlib.Path('/sys/fs/cgroup/leroyparity.slice/memory.low').read_text().strip()==str(448*1024**2)
work.mkdir(mode=0o700)
for name,encoded,mode in [('agent.py',SOURCE,0o500),('config.json',CONFIG,0o600)]:
 p=work/name;raw=base64.b64decode(encoded)
 with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 p.chmod(mode)
assert hashlib.sha256((work/'config.json').read_bytes()).hexdigest()==CONFIG_SHA
args=['systemd-run','--quiet','--collect','--unit='+UNIT,'--slice=leroyparity.slice',
 '-p','MemoryAccounting=yes','-p','MemoryLow=32M','-p','MemoryMax=128M','-p','MemorySwapMax=0',
 '-p','CPUQuota=50%','-p','TasksMax=64','-p','KillMode=control-group','-p','TimeoutStopSec=15','-p','RuntimeMaxSec=1250',
 '/usr/bin/python3','-B',str(work/'agent.py'),str(work/'config.json'),CONFIG_SHA]
r=subprocess.run(args,capture_output=True,text=True,timeout=30)
assert r.returncode==0,'Owned capacity unit launch failed; retain staged evidence'
print(json.dumps({'directory':DIRECTORY,'unit':UNIT,'config_sha256':CONFIG_SHA,'at_epoch':time.time(),'one_shot':True}))
''')
    (folder / (engine + '-nas-capacity-launch.py')).write_text(launch)
    until = min(time.monotonic() + RUNTIME_SECONDS + 60,
                time.monotonic() + approval['absolute_deadline_epoch'] - 900 - time.time())
    try:
        launched = json.loads(vm.remote(launch, sudo=True, timeout=90))
        (folder / (engine + '-nas-capacity-launched.json')).write_text(json.dumps(launched, indent=2) + '\n')
    except (vm.SSHTransportUnavailable, subprocess.TimeoutExpired) as error:
        (folder / (engine + '-nas-capacity-launch-unknown.json')).write_text(json.dumps(
            {'error_type': type(error).__name__, 'outcome_unknown': True, 'launch_repeated': False}) + '\n')
    read = 'EXPECTED=' + repr(retained) + '\n' + r'''
import hashlib,json,pathlib,subprocess,time
root=pathlib.Path(EXPECTED['directory']);assert root.parent==pathlib.Path('/volume1/docker/leroy-nas-parity')
assert root.resolve()==root and not root.is_symlink()
out={'at_epoch':time.time(),'directory':str(root),'files':{}}
if root.exists():
 assert root.stat().st_uid==0 and root.stat().st_mode&0o077==0
 for name,key in [('agent.py','source_sha256'),('config.json','config_sha256')]:
  p=root/name;assert p.resolve(strict=True)==p and p.stat().st_uid==0 and p.stat().st_mode&0o077==0
  assert hashlib.sha256(p.read_bytes()).hexdigest()==EXPECTED[key]
 for name in ('identity.json','started.json','result.json','failed.json'):
  p=root/name
  if p.exists():
   assert p.resolve(strict=True)==p and p.stat().st_uid==0 and p.stat().st_size<1024**2
   out['files'][name]=json.loads(p.read_text())
 p=root/'events.jsonl'
 if p.exists():
  assert p.resolve(strict=True)==p and p.stat().st_uid==0 and p.stat().st_size<1024**2
  out['events']=[json.loads(l) for l in p.read_text().splitlines()]
 r=subprocess.run(['systemctl','show',EXPECTED['unit'],'-p','ActiveState','--value'],capture_output=True,text=True,timeout=10)
 assert r.returncode==0
 out['unit_active_state']=r.stdout.strip() or 'unloaded'
print(json.dumps(out))
'''
    while time.monotonic() < until:
        try:
            state = json.loads(vm.remote(read, sudo=True, timeout=min(30, max(1, until - time.monotonic()))))
        except (vm.SSHTransportUnavailable, subprocess.TimeoutExpired) as error:
            with (folder / (engine + '-nas-capacity-read-unknown.jsonl')).open('a') as stream:
                stream.write(json.dumps({'at_epoch': time.time(), 'error_type': type(error).__name__,
                                         'outcome_unknown': True, 'launch_repeated': False}) + '\n')
        else:
            (folder / (engine + '-nas-capacity-latest.json')).write_text(json.dumps(state, indent=2) + '\n')
            files = state['files']
            if 'started.json' in files:
                (folder / (engine + '-file-memory-capacity-started.json')).write_text(json.dumps(files['started.json'], indent=2) + '\n')
            phases = [row['value'] for row in state.get('events', []) if row['kind'] == 'phase']
            (folder / (engine + '-file-memory-capacity-phases.jsonl')).write_text(''.join(json.dumps(p) + '\n' for p in phases))
            assert 'failed.json' not in files, 'NAS capacity driver failed; retain original evidence'
            if 'result.json' in files:
                value = files['result.json']
                validate_result(value, config, config_sha)
                if state.get('unit_active_state') in {'inactive', 'unloaded'}:
                    marker.write_text(json.dumps(value, indent=2) + '\n')
                    return value
            elif state.get('unit_active_state') in {'failed', 'inactive', 'unloaded'}:
                raise RuntimeError('NAS driver ended without a complete capacity receipt; never restart it')
        time.sleep(min(35, max(0, until - time.monotonic())))
    raise TimeoutError('NAS capacity outcome remains unknown; fixed window and NAS watchdog remain authoritative')
