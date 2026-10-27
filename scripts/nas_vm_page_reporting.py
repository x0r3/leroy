"""Report smaller unused page blocks from the own KVM guest, without shrinking RAM.

This is an explicitly separate test profile. Host kernel settings, application
sources, tests, fixture limits and the VM safety reserves remain unchanged.
"""

import json
from datetime import datetime, timezone

import nas_release_vm as vm

ORDER = 4
PROGRAM = r'''
import json,os,pathlib,subprocess,time
assert os.geteuid()==0 and pathlib.Path('/var/lib/leroy-vm/ready').is_file()
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip()=='kvm'
parameter=pathlib.Path('/sys/module/page_reporting/parameters/page_reporting_order')
assert parameter.is_file() and not parameter.is_symlink()
assert any(path.resolve().name=='virtio_balloon' for path in pathlib.Path('/sys/bus/virtio/devices').glob('*/driver'))
boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
before=int(parameter.read_text())
if PREVIOUS is not None:
 assert PREVIOUS['guest_boot_id']==boot_id and before==ORDER
else:
 assert before==9, 'Unexpected baseline parameter; retain preparation and investigate'
 parameter.write_text(str(ORDER)+'\n')
assert int(parameter.read_text())==ORDER
def memory():
 return {line.split(':')[0]:int(line.split()[1]) for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:','MemAvailable:','MemFree:','Cached:','AnonPages:','SwapTotal:','SwapFree:'))}
time.sleep(5)
print(json.dumps({'guest_boot_id':boot_id,'original_order':PREVIOUS['original_order'] if PREVIOUS else before,
 'configured_order':int(parameter.read_text()),'base_page_bytes':os.sysconf('SC_PAGE_SIZE'),
 'minimum_reported_block_bytes':os.sysconf('SC_PAGE_SIZE')*(1<<ORDER),
 'guest_memory_kib':memory(),'guest_buddyinfo':pathlib.Path('/proc/buddyinfo').read_text(),
 'guest_capacity_changed':False,'host_kernel_modified':False,'fixture_resource_limits_changed':False,
 'application_source_changed':False,'application_tests_changed':False}))
'''


def apply_guest_page_reporting(folder, engine, *, order=ORDER):
    assert type(order) is int and order in {0, 4}, 'Explicitly qualified page-reporting orders only'
    assert engine in {'jenkins', 'leroy'}
    assert folder.name == vm.ROUND
    info = vm.state()
    assert info['State']['Running']
    assert info['Config']['Labels']['io.leroy.comparison'] == vm.ROUND
    assert info['Config']['Labels']['io.leroy.engine'] == engine
    assert info['Config']['Labels']['io.leroy.nas-release-target'] == vm.COMMIT
    marker = folder / (engine + '-guest-page-reporting.json')
    previous = json.loads(marker.read_text()) if marker.exists() else None
    if previous is not None:
        assert previous['configured_order'] == order, 'Retain the original reporting configuration'
    value = json.loads(vm.guest('sudo python3 -B -',
        'ORDER=' + repr(order) + '\nPREVIOUS=' + repr(previous) + '\n' + PROGRAM, timeout=45))
    assert value['configured_order'] == order and value['original_order'] == 9
    assert value['base_page_bytes'] == 4096 and value['minimum_reported_block_bytes'] == 4096 * (1 << order)
    after = vm.state()
    assert after['Id'] == info['Id'] and after['State']['Running']
    if previous is None:
        marker.write_text(json.dumps({'at': datetime.now(timezone.utc).isoformat(), **value}, indent=2) + '\n')
    else:
        assert value['guest_boot_id'] == previous['guest_boot_id']
    return value
