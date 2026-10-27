"""Private SSD backing for test-VM RAM; no NAS swap or global kernel changes."""

import argparse
import json

import nas_release_vm as vm
from nas_ssh import ROOT, upload_file

PROOF = vm.LOCAL / 'staged-file-memory-v1.json'
LAUNCHER = vm.SSD_ROOT + '/file-memory-v1/launch.py'


def launcher_binding(version):
    assert version in {'v1', 'v2'}
    return vm.LOCAL / ('staged-file-memory-' + version + '.json'), vm.SSD_ROOT + '/file-memory-' + version + '/launch.py'


def require_launcher(baseline):
    version = 'v2' if vm.RESOURCE_PROFILE == vm.DISK_QOS_FILE_MEMORY_PROFILE else 'v1'
    path, launcher = launcher_binding(version)
    proof = json.loads(path.read_text())
    assert proof['launcher'] == launcher == vm.LAUNCHER
    assert proof['launcher_sha256'] == vm.digest(ROOT / 'infra/vm/launch.py')
    assert proof['baseline_launcher_sha256'] == baseline['launcher_sha256']
    assert proof['baseline_sha256'] == baseline['baseline_sha256']
    assert proof['qemu_image_id'] == json.loads((vm.LOCAL / 'staged.json').read_text())['qemu_image_id']
    assert proof['host_swap_changed'] is False and proof['old_launcher_retained'] is True
    code = ('import hashlib,pathlib\np=pathlib.Path(' + repr(launcher) + ')\n'
            'assert p.resolve()==p and not p.is_symlink() and p.stat().st_uid==0\n'
            'assert p.stat().st_mode&0o777==0o444 and p.parent.stat().st_mode&0o777==0o700\n'
            'assert hashlib.sha256(p.read_bytes()).hexdigest()==' + repr(proof['launcher_sha256']) + '\n'
            "print('verified')\n")
    assert vm.remote(code, sudo=True, timeout=30).strip() == 'verified'
    return proof


def stage_launcher(version='v1'):
    from nas_followup_support import inner, production_jobs
    from nas_gitea_target import idle

    path, launcher = launcher_binding(version)
    assert not path.exists(), 'Retain and inspect the existing candidate deployment'
    idle()
    assert not vm.state()['State']['Running']
    assert inner('inspect', 'jenkins-parity', '--format', '{{.State.Running}}').strip() == 'false'
    before = production_jobs()
    assert not before['active_builds']
    capability = json.loads((ROOT / 'test-results/nas-parity/followup/qemu-file-memory-capability-20261015.json').read_text())
    assert capability['kvm_file_memory_supported'] and capability['shared_file_mapping_verified']
    if version == 'v2':
        disk_qos = json.loads((ROOT / 'test-results/nas-parity/followup/qemu-disk-qos-capability-20261015.json').read_text())
        assert disk_qos['separate_disk_and_ram_qos_supported'] and disk_qos['qemu_image'] == capability['qemu_image']
        assert disk_qos['disk_read_bps'] == 128 * 1024**2 and disk_qos['disk_write_bps'] == 32 * 1024**2
    baseline = json.loads((vm.LOCAL / 'staged-ssd.json').read_text())
    source = ROOT / 'infra/vm/launch.py'
    staging = vm.REMOTE + '/file-memory-input-' + version
    vm.remote('import pathlib\np=pathlib.Path(' + repr(staging) + ')\n'
              'assert not p.exists() and p.parent.resolve()==p.parent\np.mkdir(mode=0o700)\n')
    upload_file(source, staging + '/launch.py', vm.CREDENTIALS)
    constants = {'SOURCE': staging + '/launch.py', 'DEST': launcher, 'EXPECTED': vm.digest(source),
                 'OLD': vm.SSD_ROOT + '/baseline/launch.py', 'OLD_SHA': baseline['launcher_sha256']}
    code = ''.join(k + '=' + repr(v) + '\n' for k, v in constants.items()) + r'''
import hashlib,json,os,pathlib
owner=pathlib.Path('/overlay/leroy-nas-parity-release-test');assert (owner/'.leroy-owned').is_file()
source=pathlib.Path(SOURCE);dest=pathlib.Path(DEST);old=pathlib.Path(OLD)
assert dest.is_relative_to(owner) and old.is_relative_to(owner)
assert source.resolve()==source and not source.is_symlink()
data=source.read_bytes();assert hashlib.sha256(data).hexdigest()==EXPECTED
assert old.resolve()==old and hashlib.sha256(old.read_bytes()).hexdigest()==OLD_SHA
assert not dest.parent.exists();dest.parent.mkdir(mode=0o700)
with dest.open('xb') as stream:
 stream.write(data);stream.flush();os.fsync(stream.fileno())
dest.chmod(0o444);assert hashlib.sha256(dest.read_bytes()).hexdigest()==EXPECTED
fd=os.open(dest.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
assert hashlib.sha256(old.read_bytes()).hexdigest()==OLD_SHA
print(json.dumps({'launcher':str(dest),'launcher_sha256':EXPECTED,'baseline_launcher_sha256':OLD_SHA,
 'old_launcher_retained':True,'host_swap_changed':False}))
'''
    proof = json.loads(vm.remote(code, sudo=True, timeout=45))
    assert before['jobs'] == production_jobs()['jobs']
    proof.update(baseline_sha256=baseline['baseline_sha256'], qemu_image_id=capability['qemu_image'])
    path.write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof), flush=True)


def prepare_memory_file(engine):
    assert vm.RESOURCE_PROFILE in vm.FILE_MEMORY_PROFILES and engine in {'leroy', 'jenkins'}
    assert vm.ROUND is not None
    folder = ROOT / 'test-results/nas-parity/followup' / vm.ROUND
    marker = folder / (engine + '-file-memory.json')
    assert folder.is_dir() and not marker.exists()
    constants = {'DIRECTORY': vm.SSD_ROOT + '/ram/' + vm.ROUND + '/' + engine,
                 'SIZE': vm.GUEST_MEMORY_MB * 1024**2, 'ROUND': vm.ROUND, 'ENGINE': engine, 'COMMIT': vm.COMMIT}
    code = ''.join(k + '=' + repr(v) + '\n' for k, v in constants.items()) + r'''
import json,os,pathlib,shutil,time
owner=pathlib.Path('/overlay/leroy-nas-parity-release-test');assert (owner/'.leroy-owned').is_file()
root=pathlib.Path(DIRECTORY)
assert root.is_relative_to(owner/'0ad540dd5780/ram') and not root.exists()
assert shutil.disk_usage(owner).free>=SIZE+40*1024**3
root.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
assert root.parent.resolve()==root.parent;root.mkdir(mode=0o700)
path=root/'ram.bin';fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
try:os.ftruncate(fd,SIZE);os.fsync(fd)
finally:os.close(fd)
info=path.stat();assert info.st_size==SIZE and info.st_uid==0 and info.st_nlink==1
value={'directory':str(root),'path':str(path),'size_bytes':SIZE,'inode':info.st_ino,
 'round':ROUND,'engine':ENGINE,'commit':COMMIT,'created_at_epoch':time.time(),
 'backend':'file','shared':True,'host_swap_changed':False}
p=root/'prepared.json';p.write_text(json.dumps(value));p.chmod(0o600)
print(json.dumps(value))
'''
    value = json.loads(vm.remote(code, sudo=True, timeout=45))
    marker.write_text(json.dumps(value, indent=2) + '\n')
    return value


def observe_file_memory():
    assert vm.RESOURCE_PROFILE in vm.FILE_MEMORY_PROFILES
    constants = {'ROUND': vm.ROUND, 'COMMIT': vm.COMMIT, 'SIZE': vm.GUEST_MEMORY_MB * 1024**2}
    code = ''.join(k + '=' + repr(v) + '\n' for k, v in constants.items()) + r'''
import json,pathlib,socket,subprocess
info=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-release-target-vm'],text=True,timeout=15))[0]
labels=info['Config']['Labels'];assert labels['io.leroy.comparison']==ROUND and labels['io.leroy.nas-release-target']==COMMIT
assert info['State']['Running'] and 'VM_MEMORY_FILE=/vm-memory/ram.bin' in info['Config']['Env']
pid=info['State']['Pid'];process=pathlib.Path('/proc',str(pid))
ticks=(process/'stat').read_text().rpartition(') ')[2].split()[19]
with socket.socket(socket.AF_UNIX) as connection:
 connection.settimeout(10);connection.connect(str(process/'root/run/qmp.sock'));stream=connection.makefile('rwb',buffering=0)
 assert 'QMP' in json.loads(stream.readline(65536))
 def request(command,arguments=None):
  stream.write((json.dumps({'execute':command,**({'arguments':arguments} if arguments else {})})+'\n').encode())
  while True:
   value=json.loads(stream.readline(65536))
   if 'event' in value:continue
   assert 'return' in value,'Test-VM QMP property unavailable'
   return value['return']
 request('qmp_capabilities')
 properties={key:request('qom-get',{'path':'/objects/leroyram','property':key})
             for key in ('share','size','mem-path','prealloc','dump')}
assert properties=={'share':True,'size':SIZE,'mem-path':'/vm-memory/ram.bin','prealloc':False,'dump':False}
assert (process/'stat').read_text().rpartition(') ')[2].split()[19]==ticks
print(json.dumps({'backend':'file','size_bytes':SIZE,'shared':True,'preallocated':False,'dump':False,
 'host_swap_changed':False,'qmp_verified':True}))
'''
    return json.loads(vm.remote(code, sudo=True, timeout=40))


def release_memory_file(folder, engine):
    expected = json.loads((folder / (engine + '-file-memory.json')).read_text())
    assert expected['round'] == folder.name and expected['engine'] == engine and expected['commit'] == vm.COMMIT
    code = 'EXPECTED=' + repr(expected) + '\n' + r'''
import json,os,pathlib,stat,subprocess,time
info=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-release-target-vm'],text=True,timeout=15))[0]
assert not info['State']['Running']
labels=info['Config']['Labels'];assert labels['io.leroy.comparison']==EXPECTED['round'] and labels['io.leroy.engine']==EXPECTED['engine']
assert labels['io.leroy.nas-release-target']==EXPECTED['commit']
root=pathlib.Path(EXPECTED['directory']);path=root/'ram.bin'
assert root==pathlib.Path('/overlay/leroy-nas-parity-release-test/0ad540dd5780/ram')/EXPECTED['round']/EXPECTED['engine']
assert root.resolve()==root and not (root/'released.json').exists()
assert json.loads((root/'prepared.json').read_text())==EXPECTED
assert path.resolve()==path and not path.is_symlink()
value=path.stat();assert value.st_ino==EXPECTED['inode'] and value.st_nlink==1 and value.st_size==EXPECTED['size_bytes']
assert value.st_uid==0 and stat.S_IMODE(value.st_mode)==0o600
path.unlink();fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
proof={'released_after_vm_stopped':True,'bytes':EXPECTED['size_bytes'],'round':EXPECTED['round'],
 'engine':EXPECTED['engine'],'at_epoch':time.time(),'disk_snapshots_removed':False}
p=root/'released.json';p.write_text(json.dumps(proof));p.chmod(0o600);print(json.dumps(proof))
'''
    proof = json.loads(vm.remote(code, sudo=True, timeout=40))
    (folder / (engine + '-file-memory-released.json')).write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def verify_paired_environment(folder):
    expected = {'backend': 'file', 'size_bytes': vm.GUEST_MEMORY_MB * 1024**2, 'shared': True,
                'preallocated': False, 'dump': False, 'host_swap_changed': False, 'qmp_verified': True}
    for engine in ('leroy', 'jenkins'):
        before = json.loads((folder / (engine + '-target-before.json')).read_text())
        assert before['file_memory_configuration'] == expected
        if vm.RESOURCE_PROFILE == vm.DISK_QOS_FILE_MEMORY_PROFILE:
            for suffix in ('-target-before.json', '-target-after.json'):
                path = folder / (engine + suffix)
                if path.exists():
                    snapshot = json.loads(path.read_text())
                    assert snapshot['guest_disk_io_throttle'] == {'read_bps': 128 * 1024**2, 'write_bps': 32 * 1024**2}
                    assert snapshot['outer_vm_io_limits'] == {'BlkioDeviceReadBps': [], 'BlkioDeviceWriteBps': []}
        if vm.RESOURCE_PROFILE in vm.PROTECTED_FILE_MEMORY_PROFILES:
            pressure = before['outer_vm_memory_pressure']
            assert pressure['memory_low_bytes'] == pressure['memory_reservation_bytes'] == 4 * 1024**3
            assert pressure['memory_high_bytes'] == 5 * 1024**3 and pressure['cgroup_parent'] == '-.slice'
        path = folder / (engine + '-target-after.json')
        if path.exists():
            after = json.loads(path.read_text())
            assert after['file_memory_configuration'] == expected
            if vm.RESOURCE_PROFILE in vm.PROTECTED_FILE_MEMORY_PROFILES:
                for key in ('memory_low_bytes', 'memory_reservation_bytes', 'memory_high_bytes', 'cgroup_parent'):
                    assert after['outer_vm_memory_pressure'][key] == before['outer_vm_memory_pressure'][key]
        prepared_path = folder / 'prepared.json'
        prepared = json.loads(prepared_path.read_text()) if prepared_path.exists() else {}
        if prepared.get('original_workload_qualification'):
            from nas_original_workload import verify_retained

            assert prepared['synthetic_capacity_qualified'] is False
            verify_retained(folder, engine)
            continue
        proof = json.loads((folder / (engine + '-file-memory-capacity.json')).read_text())
        assert proof['qualified_synthetic_capacity'] and proof['all_page_markers_intact']
        assert proof['allocated_mib'] == 5888 and proof['hold_seconds'] == 60
        assert proof['original_fixture_limits_emulated'] is True
        assert proof['limits']['memory_bytes'] == proof['limits']['memory_and_swap_bytes'] == 6 * 1024**3
        assert proof['limits']['nano_cpus'] == 2 * 10**9 and proof['limits']['cgroup_swap_max'] == 0
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage-launcher', action='store_true', required=True)
    parser.add_argument('--version', choices=('v1', 'v2'), default='v1')
    args = parser.parse_args()
    stage_launcher(args.version)


if __name__ == '__main__':
    main()
