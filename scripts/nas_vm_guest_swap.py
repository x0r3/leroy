"""Candidate SSD swap inside the owned KVM guest; never change NAS swap or fixtures."""

import json

import nas_release_vm as vm

SWAP_BYTES = 4 * 1024**3
PROGRAM = r'''
import json,os,pathlib,shutil,stat,subprocess

def write_swap_file(path,size):
 assert size>0 and size%(8*1024**2)==0
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  block=bytes(8*1024**2);processed=0
  for _ in range(size//len(block)):
   view=memoryview(block)
   while view:
    count=os.write(fd,view);assert count>0;view=view[count:]
   processed+=len(block)
   if processed%(64*1024**2)==0:
    os.fdatasync(fd)
    os.posix_fadvise(fd,processed-64*1024**2,64*1024**2,os.POSIX_FADV_DONTNEED)
  os.fsync(fd)
 finally:os.close(fd)

assert os.geteuid()==0 and pathlib.Path('/var/lib/leroy-vm/ready').is_file()
assert subprocess.check_output(['systemd-detect-virt'],text=True,timeout=10).strip()=='kvm'
root=pathlib.Path('/var/lib/leroy-vm/guest-swap')
assert root.resolve()==root and not root.is_symlink() and not root.exists()
assert not pathlib.Path('/proc/swaps').read_text().splitlines()[1:]
assert shutil.disk_usage(root.parent).free>=SIZE+12*1024**3
root.mkdir(mode=0o700);path=root/'swapfile'
write_swap_file(path,SIZE)
assert stat.S_ISREG(path.stat().st_mode) and path.stat().st_size==SIZE and path.stat().st_mode&0o777==0o600
for command in (['mkswap',str(path)],['swapon','--priority','10',str(path)]):
 subprocess.run(command,check=True,capture_output=True,text=True,timeout=30)
rows=pathlib.Path('/proc/swaps').read_text().splitlines()[1:]
assert len(rows)==1
parts=rows[0].split();assert parts[0]==str(path) and parts[1]=='file'
assert SIZE//1024-16<=int(parts[2])<=SIZE//1024
print(json.dumps({'guest_swap_file':str(path),'guest_swap_bytes':SIZE,
 'kernel_swap_kib':int(parts[2]),'priority':int(parts[4]),'guest_swappiness':int(pathlib.Path('/proc/sys/vm/swappiness').read_text()),
 'preparation_cache_hint_interval_bytes':64*1024**2,
 'persistent_boot_configuration_changed':False,'host_swap_changed':False,'fixture_resource_limits_changed':False,
 'application_source_changed':False,'application_tests_changed':False}))
'''


def apply_guest_swap(folder, engine):
    assert engine in {'leroy', 'jenkins'} and folder.name == vm.ROUND
    assert vm.RESOURCE_PROFILE in vm.GUEST_SWAP_PROFILES
    info = vm.state()
    labels = info['Config']['Labels']
    assert info['State']['Running'] and labels['io.leroy.nas-release-target'] == vm.COMMIT
    assert labels['io.leroy.comparison'] == vm.ROUND and labels['io.leroy.engine'] == engine
    marker = folder / (engine + '-guest-swap.json')
    assert not marker.exists(), 'Retain the existing candidate environment; never reset its swap'
    proof = json.loads(vm.guest('sudo python3 -B -', 'SIZE=' + repr(SWAP_BYTES) + '\n' + PROGRAM, timeout=300))
    assert proof['guest_swap_bytes'] == SWAP_BYTES and not proof['host_swap_changed']
    marker.write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def observe_guest_swap():
    return json.loads(vm.guest('sudo python3 -B -', r'''
import json,pathlib,stat
path=pathlib.Path('/var/lib/leroy-vm/guest-swap/swapfile')
assert path.resolve()==path and not path.is_symlink() and path.stat().st_size==4*1024**3
assert stat.S_ISREG(path.stat().st_mode) and path.stat().st_mode&0o777==0o600
rows=pathlib.Path('/proc/swaps').read_text().splitlines()[1:];assert len(rows)==1
parts=rows[0].split();assert parts[0]==str(path) and parts[1]=='file'
assert 4*1024**2-16<=int(parts[2])<=4*1024**2
print(json.dumps({'path':str(path),'file_bytes':path.stat().st_size,'kernel_swap_kib':int(parts[2]),
 'priority':int(parts[4]),'swappiness':int(pathlib.Path('/proc/sys/vm/swappiness').read_text())}))
''', timeout=45))
