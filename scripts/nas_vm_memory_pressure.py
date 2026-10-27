"""Apply early reclaim only to the explicitly owned test VM's cgroup.

The guest capacity, Docker hard limits, original fixture limits and global NAS
kernel settings remain unchanged. Both CI engines use this separate profile.
"""

import json
from datetime import datetime, timezone

import nas_release_vm as vm

HIGH_BYTES = 3 * 1024**3
PROFILE_HIGH_BYTES = {'nas-6g-ssd-soft-ram': HIGH_BYTES,
                      'nas-6g-ssd-soft-ram-3328': HIGH_BYTES + 256 * 1024**2,
                      'nas-6g-ssd-soft-ram-3584': HIGH_BYTES + 512 * 1024**2,
                      'nas-10g-ssd-soft-ram-4096': 4 * 1024**3,
                      'nas-10g-ssd-soft-ram-3584': 3584 * 1024**2,
                      'nas-8g-ssd-soft-ram-3584': 3584 * 1024**2,
                      'nas-8g-ssd-soft-ram-3840': 3840 * 1024**2,
                      'nas-8g-ssd-soft-ram-4096': 4096 * 1024**2,
                      vm.GUEST_SWAP_PROFILE: 3840 * 1024**2,
                      vm.BOUNDED_GUEST_SWAP_PROFILE: 3840 * 1024**2,
                      vm.FILE_MEMORY_PROFILE: 3840 * 1024**2,
                      vm.PROTECTED_FILE_MEMORY_PROFILE: 5120 * 1024**2,
                      vm.DISK_QOS_FILE_MEMORY_PROFILE: 5120 * 1024**2}
PROGRAM = r'''
import json,os,pathlib,subprocess
assert os.geteuid()==0
expected_max=globals().get('EXPECTED_MAX',7*1024**3)
expected_total=globals().get('EXPECTED_TOTAL',10*1024**3)
assert (expected_max,expected_total) in {(7*1024**3,10*1024**3),(9*1024**3,13*1024**3),(11*1024**3,15*1024**3)}
def inspect():
 info=json.loads(subprocess.check_output(['docker','inspect',CONTAINER],text=True,timeout=15))[0]
 assert info['State']['Running'] and info['State']['Pid']>0
 assert info['Config']['Labels']['io.leroy.nas-release-target']==COMMIT
 assert info['Config']['Labels']['io.leroy.comparison']==ROUND
 assert info['Config']['Labels']['io.leroy.engine']==ENGINE
 assert info['HostConfig']['Memory']==expected_max and info['HostConfig']['MemorySwap']==expected_total
 return info
info=inspect();pid=info['State']['Pid']
protected=globals().get('PROTECTED',False)
if protected:
 assert info['HostConfig']['CgroupParent']=='-.slice' and info['HostConfig']['MemoryReservation']==4*1024**3
 system=pathlib.Path('/sys/fs/cgroup/system.slice')
 for name in ('memory.max','memory.high','memory.swap.max','pids.max'):
  assert (system/name).read_text().strip()=='max','Never bypass an existing system.slice hard/throttle limit'
 assert (system/'cpu.max').read_text().split()[0]=='max' and not (system/'io.max').read_text().strip()
process=pathlib.Path('/proc')/str(pid)
start_ticks=process.joinpath('stat').read_text().rpartition(') ')[2].split()[19]
records=process.joinpath('cgroup').read_text().splitlines()
unified=[line[3:] for line in records if line.startswith('0::')]
assert len(unified)==1
relative=pathlib.PurePosixPath(unified[0])
assert relative.is_absolute() and '..' not in relative.parts and len(relative.parts)>1
assert relative.name in {info['Id'],'docker-'+info['Id']+'.scope'}
root=pathlib.Path('/sys/fs/cgroup').resolve(strict=True)
assert root.joinpath('cgroup.controllers').is_file()
directory=root.joinpath(*relative.parts[1:])
assert directory.resolve(strict=True)==directory and directory.is_relative_to(root) and directory!=root
if protected:
 assert directory.parent==root and int((directory/'memory.low').read_text())==4*1024**3
parameter=directory/'memory.high'
assert parameter.is_file() and not parameter.is_symlink()
assert int((directory/'memory.max').read_text())==expected_max
assert int((directory/'memory.swap.max').read_text())==expected_total-expected_max
before=parameter.read_text().strip()
if APPLY:
 if PREVIOUS is None:
  assert before=='max', 'Unexpected pre-existing memory.high; retain preparation'
 else:
  assert PREVIOUS['container_id']==info['Id'] and PREVIOUS['process_start_ticks']==start_ticks
  assert before==str(HIGH)
 if PREVIOUS is None:
  descriptor=os.open(parameter,os.O_WRONLY|os.O_NONBLOCK|os.O_NOFOLLOW)
  try:
   data=(str(HIGH)+'\n').encode()
   assert os.write(descriptor,data)==len(data)
  finally:os.close(descriptor)
assert parameter.read_text().strip()==str(HIGH)
after=inspect()
assert after['Id']==info['Id'] and after['State']['Pid']==pid
assert process.joinpath('stat').read_text().rpartition(') ')[2].split()[19]==start_ticks
events={key:int(value) for key,value in (line.split() for line in (directory/'memory.events').read_text().splitlines() if line.strip())}
print(json.dumps({'container_id':info['Id'],'process_start_ticks':start_ticks,'cgroup_path':str(directory),
 'memory_high_before_operation':before,
 'original_memory_high':(PREVIOUS['original_memory_high'] if PREVIOUS is not None else before) if APPLY else None,
 'memory_high_bytes':int(parameter.read_text()),'memory_max_bytes':int((directory/'memory.max').read_text()),
 'memory_swap_max_bytes':int((directory/'memory.swap.max').read_text()),
 'memory_current_bytes':int((directory/'memory.current').read_text()),
 'memory_swap_current_bytes':int((directory/'memory.swap.current').read_text()),'events':events,
 'memory_low_bytes':int((directory/'memory.low').read_text()),'cgroup_parent':info['HostConfig']['CgroupParent'],
 'memory_reservation_bytes':info['HostConfig']['MemoryReservation'],
 'guest_capacity_changed':False,'global_host_kernel_settings_changed':False,'fixture_resource_limits_changed':False,
 'application_source_changed':False,'application_tests_changed':False}))
'''


def high_bytes_for_profile(profile):
    assert profile in PROFILE_HIGH_BYTES, 'Owned memory pressure profile required'
    return PROFILE_HIGH_BYTES[profile]


def observe_outer_memory_pressure(engine, *, apply=False, previous=None):
    assert engine in {'jenkins', 'leroy'} and vm.ROUND is not None
    high = high_bytes_for_profile(vm.RESOURCE_PROFILE)
    value = json.loads(vm.remote('CONTAINER=' + repr(vm.CONTAINER) + '\nCOMMIT=' + repr(vm.COMMIT) +
        '\nROUND=' + repr(vm.ROUND) + '\nENGINE=' + repr(engine) + '\nHIGH=' + repr(high) +
        '\nEXPECTED_MAX=' + repr(vm.CONTAINER_MEMORY_GIB*1024**3) + '\nEXPECTED_TOTAL=' + repr(vm.CONTAINER_MEMORY_SWAP_GIB*1024**3) +
        '\nPROTECTED=' + repr(vm.RESOURCE_PROFILE in vm.PROTECTED_FILE_MEMORY_PROFILES) +
        '\nAPPLY=' + repr(apply) + '\nPREVIOUS=' + repr(previous) + '\n' + PROGRAM, sudo=True, timeout=45))
    assert value['memory_high_bytes'] == high
    return value


def apply_outer_memory_pressure(folder, engine):
    assert folder.name == vm.ROUND and vm.RESOURCE_PROFILE in vm.MEMORY_PRESSURE_PROFILES
    marker = folder / (engine + '-outer-memory-pressure.json')
    previous = json.loads(marker.read_text(encoding='utf-8')) if marker.exists() else None
    value = observe_outer_memory_pressure(engine, apply=True, previous=previous)
    if previous is None:
        marker.write_text(json.dumps({'at': datetime.now(timezone.utc).isoformat(), **value}, indent=2) + '\n', encoding='utf-8')
    return value
