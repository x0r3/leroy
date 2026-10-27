"""Own-kernel release target on the NAS, restored from an immutable original snapshot.

Only the explicitly owned test directory and container are changed. The Windows
VM is never booted. Existing snapshots and per-engine overlays remain retained.
"""

import argparse
import base64
import hashlib
import json
import re
import subprocess
import time
import uuid

from nas_ssh import ROOT, run_script, upload_file
from nas_verified_container import discover_program, verify_program

COMMIT = '0ad540dd578033d45e4d0c25d89fbe57b32102a4'
SNAPSHOT = 'graphato-existing-host-0ad540dd5780'
LOCAL = ROOT / '.local/nas-full-release' / COMMIT[:12]
REMOTE = '/volume1/docker/leroy-nas-parity/release-vm/' + COMMIT[:12]
SSD_ROOT = '/overlay/leroy-nas-parity-release-test/' + COMMIT[:12]
BASELINE_ROOT = REMOTE
DISK_ROOT = REMOTE
LAUNCHER = REMOTE + '/launch.py'
MIN_DISK_FREE_MB = 0
CONTAINER = 'leroy-nas-release-target-vm'
CREDENTIALS = ROOT / '.local/nas-ssh.json'
ROUND = None
GUEST_MEMORY_MB = 4608
CONTAINER_MEMORY_GIB = 6
CONTAINER_MEMORY_SWAP_GIB = 9
DISK_CACHE = 'writeback'
MIN_HOST_SWAP_MB = 2304
MIN_HOST_AVAILABLE_MB = 128
RESOURCE_PROFILE = 'nas-4g5'
GUEST_SWAP_PROFILE = 'nas-8g-ssd-guest-swap-3840'
BOUNDED_GUEST_SWAP_PROFILE = 'nas-7g-ssd-guest-swap-3840'
FILE_MEMORY_PROFILE = 'nas-7g-ssd-file-memory-3840'
PROTECTED_FILE_MEMORY_PROFILE = 'nas-7g-ssd-file-memory-protected'
DISK_QOS_FILE_MEMORY_PROFILE = 'nas-7g-ssd-file-memory-disk-qos'
PROTECTED_FILE_MEMORY_PROFILES = {PROTECTED_FILE_MEMORY_PROFILE, DISK_QOS_FILE_MEMORY_PROFILE}
FILE_MEMORY_PROFILES = {FILE_MEMORY_PROFILE, *PROTECTED_FILE_MEMORY_PROFILES}
GUEST_SWAP_PROFILES = {GUEST_SWAP_PROFILE, BOUNDED_GUEST_SWAP_PROFILE, *FILE_MEMORY_PROFILES}
VM_IO_LIMITS = None
_GUEST_PIN = None
MEMORY_PRESSURE_PROFILES = {'nas-6g-ssd-soft-ram', 'nas-6g-ssd-soft-ram-3328', 'nas-6g-ssd-soft-ram-3584',
                            'nas-10g-ssd-soft-ram-4096', 'nas-10g-ssd-soft-ram-3584',
                            'nas-8g-ssd-soft-ram-3584', 'nas-8g-ssd-soft-ram-3840',
                            'nas-8g-ssd-soft-ram-4096', *GUEST_SWAP_PROFILES}
PAGE_REPORTING_PROFILES = {'nas-6g-ssd-fine-pages', *MEMORY_PRESSURE_PROFILES}
SSD_PROFILES = {'nas-6g-ssd', 'nas-6g-ssd-proactive-cache', *PAGE_REPORTING_PROFILES}
PROACTIVE_CACHE_PROFILES = {'nas-6g-ssd-proactive-cache', *PAGE_REPORTING_PROFILES}


class SSHTransportUnavailable(OSError):
    """An SSH result is unknown; never imply that a remote action was undone."""


def ssh_transport_unavailable(result):
    # Do not turn authentication/host-key rejection or a remote assertion into
    # an observation retry. OpenSSH reserves 255 for a client/transport error;
    # additionally require a known connection diagnostic from the pinned host.
    if result.returncode != 255:
        return False
    diagnostic = result.stderr
    if ('kex_exchange_identification: read: Unknown error' in diagnostic
            and 'banner exchange: Connection to 192.168.178.97 port 22: Unknown error' in diagnostic):
        return True
    return any(value in diagnostic for value in (
        'Connection timed out during banner exchange',
        'Connection to 192.168.178.97 port 22 timed out',
        'Timeout, server 192.168.178.97 not responding.',
        'ssh: connect to host 192.168.178.97 port 22: Connection refused',
        'Connection reset by 192.168.178.97 port 22',
        'Connection closed by 192.168.178.97 port 22',
        'kex_exchange_identification: read: Connection reset by peer',
        'client_loop: send disconnect: Broken pipe',
    ))


def configure(round_name, resource_profile='nas-4g5'):
    """Pin one retained comparison namespace; never reset an earlier overlay."""
    global ROUND, RESOURCE_PROFILE, GUEST_MEMORY_MB, CONTAINER_MEMORY_GIB, CONTAINER_MEMORY_SWAP_GIB, VM_IO_LIMITS
    global BASELINE_ROOT, DISK_ROOT, LAUNCHER, MIN_DISK_FREE_MB
    global DISK_CACHE
    assert re.fullmatch('[a-z0-9-]{1,64}', round_name)
    assert ROUND is None or ROUND == round_name
    assert resource_profile in {'nas-4g5', 'nas-6g-io-limited', *SSD_PROFILES}
    assert ROUND is None or RESOURCE_PROFILE == resource_profile
    ROUND = round_name
    RESOURCE_PROFILE = resource_profile
    if resource_profile in {'nas-6g-io-limited', *SSD_PROFILES}:
        GUEST_MEMORY_MB, CONTAINER_MEMORY_GIB, CONTAINER_MEMORY_SWAP_GIB = 6144, 7, 10
        VM_IO_LIMITS = {'device': '/dev/dm-0', 'read_bps': 24 * 1024**2, 'write_bps': 8 * 1024**2}
    if resource_profile in SSD_PROFILES:
        BASELINE_ROOT, DISK_ROOT, LAUNCHER = SSD_ROOT + '/baseline', SSD_ROOT, SSD_ROOT + '/baseline/launch.py'
        MIN_DISK_FREE_MB = 40 * 1024
        VM_IO_LIMITS = {'device': '/dev/nvme0n1', 'mount_device': '/dev/nvme0n1p7',
                        'read_bps': 128 * 1024**2, 'write_bps': 32 * 1024**2}
    if resource_profile in {'nas-10g-ssd-soft-ram-4096','nas-10g-ssd-soft-ram-3584'}:
        # The original postdeploy builder itself permits 6 GiB without swap.
        # The guest also hosts the baseline release, databases and its kernel.
        GUEST_MEMORY_MB, CONTAINER_MEMORY_GIB, CONTAINER_MEMORY_SWAP_GIB = 10240, 11, 15
    if resource_profile in {'nas-8g-ssd-soft-ram-3584', 'nas-8g-ssd-soft-ram-3840', 'nas-8g-ssd-soft-ram-4096', *GUEST_SWAP_PROFILES}:
        # Separate qualification: retain the original 6-GiB no-swap builder,
        # but avoid the earlier guest's additional 2 GiB of virtual RAM.
        GUEST_MEMORY_MB, CONTAINER_MEMORY_GIB, CONTAINER_MEMORY_SWAP_GIB = 8192, 9, 13
    if resource_profile in {BOUNDED_GUEST_SWAP_PROFILE, *FILE_MEMORY_PROFILES}:
        GUEST_MEMORY_MB, CONTAINER_MEMORY_GIB, CONTAINER_MEMORY_SWAP_GIB = 7168, 9, 13
    if resource_profile in FILE_MEMORY_PROFILES:
        LAUNCHER = SSD_ROOT + '/file-memory-v1/launch.py'
    if resource_profile in PROTECTED_FILE_MEMORY_PROFILES:
        DISK_CACHE = 'none'
    if resource_profile == DISK_QOS_FILE_MEMORY_PROFILE:
        LAUNCHER = SSD_ROOT + '/file-memory-v2/launch.py'
        VM_IO_LIMITS['target'] = 'qemu-disk'


def remote(program, timeout=120, *, sudo=False):
    if sudo and len(program.encode('utf-8')) > 12000:
        # Password sudo places its shell-quoted body in the Windows SSH argv.
        # Keep large diagnostics off that command line; execute only the exact
        # privately uploaded bytes after independently checking their digest.
        payload = program.encode('utf-8')
        name = 'remote-input-' + uuid.uuid4().hex + '.py'
        LOCAL.mkdir(parents=True, exist_ok=True)
        local = LOCAL / name
        with local.open('xb') as stream:
            local.chmod(0o600)
            stream.write(payload)
        destination = REMOTE + '/' + name
        upload_file(local, destination, CREDENTIALS, timeout=min(timeout, 120))
        program = ('import hashlib,pathlib\np=pathlib.Path(' + repr(destination) + ')\n'
                   'assert p.resolve()==p and p.is_file() and not p.is_symlink()\n'
                   'assert p.stat().st_mode&0o077==0\n'
                   'raw=p.read_bytes()\nassert hashlib.sha256(raw).hexdigest()==' + repr(hashlib.sha256(payload).hexdigest()) + '\n'
                   "exec(compile(raw,'<verified-owned-remote-input>','exec'))\n")
    result = run_script("python3 - <<'PY'\n" + program + '\nPY\n', CREDENTIALS, timeout=timeout, sudo=sudo)
    if result.returncode:
        if ssh_transport_unavailable(result):
            raise SSHTransportUnavailable('NAS SSH transport unavailable; remote operation outcome is unknown')
        raise RuntimeError(result.stderr[-1800:])
    return result.stdout


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def stage():
    """Resume byte-verified uploads; do not start an application or CI job."""
    assert subprocess.check_output(['docker', 'inspect', 'leroy-nas-target-vm',
                                    '--format', '{{.State.Running}}']).strip() == b'false'
    disk = LOCAL / 'baseline.qcow2'
    info = json.loads(subprocess.check_output([
        'docker', 'run', '--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
        '--memory', '256m', '--cpus', '0.5', '--mount', f'type=bind,source={LOCAL},target=/export,readonly',
        '--entrypoint', 'qemu-img', 'leroy-vm-host:local', 'info', '--output=json', '/export/baseline.qcow2']))
    assert not info.get('backing-filename') and not info.get('snapshots')
    assert not info.get('dirty-flag') and not info['format-specific']['data']['corrupt']
    identity = {'commit': COMMIT, 'snapshot': SNAPSHOT, 'sha256': digest(disk),
                'size_bytes': disk.stat().st_size, 'virtual_size_bytes': info['virtual-size'],
                'source_volume': 'leroy-nas-target_disk', 'application_source_changed': False}
    (LOCAL / 'prepared.json').write_text(json.dumps(identity, indent=2) + '\n')
    (LOCAL / 'launch.py').write_bytes((ROOT / 'infra/vm/launch.py').read_bytes())
    (LOCAL / 'admin-key').write_bytes((ROOT / '.local/vm/id_ed25519').read_bytes())
    public = (ROOT / '.local/vm/ssh_host_ed25519_key.pub').read_text().strip()
    (LOCAL / 'known_hosts').write_text('graphato-parity ' + public + '\n[graphato-parity]:12225 ' + public + '\n')
    local_image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', 'leroy-vm-host:local']))[0]
    image = local_image['Id']
    image_file = LOCAL / 'qemu-image.tar'
    if not image_file.exists():
        subprocess.run(['docker', 'save', '-o', str(image_file), 'leroy-vm-host:local'], check=True)
    remote("import pathlib\nroot=pathlib.Path(" + repr(REMOTE) + ")\n"
           "assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()\n"
           "root.mkdir(parents=True,exist_ok=True)\n"
           "assert root.resolve()==root and not root.is_symlink()\n")
    files = ('baseline.qcow2', 'seed.img', 'uefi-vars.fd', 'prepared.json', 'launch.py',
             'admin-key', 'known_hosts', 'qemu-image.tar')
    for name in files:
        path = LOCAL / name
        sha = digest(path)
        destination = REMOTE + '/' + name
        check = json.loads(remote('import hashlib,json,pathlib\np=pathlib.Path(' + repr(destination) + ')\n'
                                  "with p.open('rb') if p.exists() else open('/dev/null','rb') as f:\n"
                                  " print(json.dumps({'exists':p.exists(),'sha256':hashlib.file_digest(f,'sha256').hexdigest()}))",
                                  timeout=600))
        if not check['exists'] or check['sha256'] != sha:
            assert name != 'baseline.qcow2' or not check['exists'], 'Never replace an existing baseline'
            print(json.dumps({'uploading': name, 'bytes': path.stat().st_size}), flush=True)
            upload_file(path, destination, CREDENTIALS, timeout=7200)
            actual = remote('import hashlib,pathlib\nwith pathlib.Path(' + repr(destination) + ").open('rb') as f:\n"
                            " print(hashlib.file_digest(f,'sha256').hexdigest())", timeout=600).strip()
            assert actual == sha, 'Uploaded asset checksum mismatch'
        print(json.dumps({'verified': name, 'sha256': sha}), flush=True)
    imported = json.loads(remote('import json,pathlib,subprocess\nroot=pathlib.Path(' + repr(REMOTE) + ')\n'
           "subprocess.run(['docker','load','-i',str(root/'qemu-image.tar')],check=True,capture_output=True,timeout=180)\n"
           "actual=json.loads(subprocess.check_output(['docker','image','inspect','leroy-vm-host:local'],text=True))[0]\n"
           "print(json.dumps({k:actual[k] for k in ('Id','Architecture','Os','RootFS','Config')}))\n"
           "for name in ('baseline.qcow2','seed.img','uefi-vars.fd','prepared.json','launch.py','known_hosts'):\n"
           " (root/name).chmod(0o444)\n(root/'admin-key').chmod(0o600)\n", timeout=240))
    # Containerd reports an OCI index ID; the classic image store reports the
    # config ID. Compare the actual filesystem/configuration instead of aliases.
    assert all(imported[key] == local_image[key] for key in ('Architecture', 'Os', 'RootFS', 'Config'))
    remote('import os,pathlib\np=pathlib.Path(' + repr(REMOTE) + ')\n'
           'assert p.resolve()==p and not p.is_symlink()\nos.chown(p,p.stat().st_uid,0)\np.chmod(0o710)\n',
           sudo=True)
    identity['qemu_export_image_id'] = image
    identity['qemu_image_id'] = imported['Id']
    identity['qemu_rootfs_layers'] = imported['RootFS']['Layers']
    identity['launcher_sha256'] = digest(LOCAL / 'launch.py')
    (LOCAL / 'staged.json').write_text(json.dumps(identity, indent=2) + '\n')
    return identity


def stage_ssd():
    """Copy only the immutable test baseline to existing NAS SSD storage while idle."""
    from contextlib import closing

    from compare_nas_antares import client
    from nas_followup_support import inner
    from nas_gitea_target import idle
    from nas_measurement_guard import begin, finish

    idle()
    info = state()
    assert not info or not info['State']['Running'], 'Do not copy disks during an original comparison'
    assert inner('inspect', 'jenkins-parity', '--format', '{{.State.Running}}').strip() == 'false'
    assert not inner('ps', '-q', '--filter', 'label=io.leroy.runner=runner-nas-parity').strip()
    with closing(client()) as api:
        assert not any(p['enabled'] for p in api.get('/api/pipelines').json())
    evidence = ROOT / 'test-results/nas-parity/followup/nas-ssd-baseline-preparation-20261011'
    evidence.mkdir(parents=True, exist_ok=True)
    identity = json.loads((LOCAL / 'staged.json').read_text())
    launcher = (ROOT / 'infra/vm/launch.py').read_bytes()
    started = evidence / 'started.json'
    inputs = {'baseline_sha256': identity['sha256'], 'launcher_sha256': hashlib.sha256(launcher).hexdigest()}
    if started.exists():
        prior = json.loads(started.read_text())
        assert all(prior[key] == value for key, value in inputs.items())
        production_before = prior['production_before']
    else:
        production_before = begin(evidence, 'ssd-stage')
        started.write_text(json.dumps({**inputs, 'production_before': production_before}, indent=2) + '\n')
    program = ('FROZEN=' + repr(COMMIT) + '\nSOURCE=' + repr(REMOTE) + '\nDESTINATION=' + repr(SSD_ROOT) + '\nEXPECTED=' +
               repr(identity['sha256']) + '\nLAUNCHER=' + repr(base64.b64encode(launcher).decode()) + '\n' + r'''
import base64,hashlib,json,os,pathlib,shutil,stat,subprocess
source=pathlib.Path(SOURCE);root=pathlib.Path(DESTINATION)
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
state=subprocess.run(['docker','inspect','leroy-nas-release-target-vm'],capture_output=True,text=True,timeout=15)
assert state.returncode==0
target=json.loads(state.stdout)[0]
assert target['Config']['Labels']['io.leroy.nas-release-target']==FROZEN and not target['State']['Running']
assert subprocess.check_output(['docker','exec','leroy-nas-parity-docker-1','docker','inspect','jenkins-parity','--format','{{.State.Running}}'],text=True,timeout=15).strip()=='false'
assert not subprocess.check_output(['docker','exec','leroy-nas-parity-docker-1','docker','ps','-q','--filter','label=io.leroy.runner=runner-nas-parity'],text=True,timeout=15).strip()
device=pathlib.Path('/dev/nvme0n1p7');assert stat.S_ISBLK(device.stat().st_mode)
mount=json.loads(subprocess.check_output(['findmnt','-J','-T','/overlay','-o','SOURCE,FSTYPE'],text=True))['filesystems'][0]
assert pathlib.Path(mount['source']).resolve()==device.resolve() and mount['fstype']=='ext4'
assert shutil.disk_usage('/overlay').free>=80*1024**3
parent=root.parent;assert parent.resolve()==parent and not parent.is_symlink()
marker=parent/'.leroy-owned'
if parent.exists():assert marker.read_text()=='Leroy isolated release targets only\n'
else:
 parent.mkdir(mode=0o700);marker.write_text('Leroy isolated release targets only\n');marker.chmod(0o600)
root.mkdir(mode=0o700,exist_ok=True);assert root.resolve()==root and not root.is_symlink()
baseline=root/'baseline';baseline.mkdir(mode=0o700,exist_ok=True)
assert baseline.resolve()==baseline and not baseline.is_symlink()
def digest(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
hashes={}
for name in ('baseline.qcow2','seed.img','uefi-vars.fd'):
 original=source/name;destination=baseline/name;assert not original.is_symlink() and not destination.is_symlink()
 expected=EXPECTED if name=='baseline.qcow2' else digest(original)
 if not destination.exists():
  temporary=destination.with_suffix(destination.suffix+'.copying');assert not temporary.exists()
  shutil.copyfile(original,temporary);assert digest(temporary)==expected
  with temporary.open('rb') as stream:os.fsync(stream.fileno())
  temporary.replace(destination);destination.chmod(0o444)
 else:assert digest(destination)==expected
 hashes[name]=expected
data=base64.b64decode(LAUNCHER);path=baseline/'launch.py';expected=hashlib.sha256(data).hexdigest()
if path.exists():assert digest(path)==expected
else:
 with path.open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
 path.chmod(0o444)
fd=os.open(baseline,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
print(json.dumps({'baseline_root':str(baseline),'baseline_sha256':hashes['baseline.qcow2'],
 'asset_sha256':hashes,'launcher_sha256':expected,'block_device':str(device),
 'device_major':os.major(device.stat().st_rdev),'device_minor':os.minor(device.stat().st_rdev),
 'filesystem':'ext4','available_bytes_after':shutil.disk_usage(root).free,
 'existing_filesystems_reformatted':False,'application_source_changed':False,
 'application_tests_changed':False,'production_modified':False}))
''')
    proof = json.loads(remote(program, timeout=600, sudo=True))
    assert proof['launcher_sha256'] == hashlib.sha256(launcher).hexdigest()
    qualification = finish(evidence, 'ssd-stage', production_before)
    proof['production_stage_qualification'] = qualification
    (LOCAL / 'staged-ssd.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof), flush=True)
    return proof


def guest(command, data=None, timeout=600):
    """Authenticated original guest SSH through the NAS, with the existing pinned key."""
    args = ['ssh', '-T', '-i', REMOTE + '/admin-key', '-p', '12225',
            '-o', 'UserKnownHostsFile=' + REMOTE + '/known_hosts', '-o', 'HostKeyAlias=graphato-parity',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
            '-o', 'ControlMaster=auto', '-o', 'ControlPersist=600',
            'leroy-admin@127.0.0.1', command]
    # Administrative checks use the owned VM's loopback network, separate from
    # original CI traffic. Reuse a connection rather than weakening host limits.
    encoded = base64.b64encode((data or '').encode()).decode()
    if len(encoded) > 8192:
        # A sudo SSH command is a Windows process argument. Large embedded
        # programs can exceed CreateProcess's limit before contacting the NAS.
        # Stage the same bytes privately; retain them for uncertain outcomes.
        name = 'guest-input-' + uuid.uuid4().hex + '.bin'
        local = LOCAL / name
        local.write_bytes((data or '').encode())
        local.chmod(0o600)
        destination = REMOTE + '/' + name
        upload_file(local, destination, CREDENTIALS)
        payload = ('p=pathlib.Path(' + repr(destination) + ')\n'
                   'assert p.resolve()==p and p.parent==pathlib.Path(' + repr(REMOTE) + ')\n'
                   'assert p.stat().st_mode & 0o077==0\n'
                   'data=p.read_bytes()\nassert hashlib.sha256(data).hexdigest()==' + repr(digest(local)) + '\n')
    else:
        payload = 'data=base64.b64decode(' + repr(encoded) + ')\n'
    global _GUEST_PIN
    if _GUEST_PIN is None:
        labels = {'io.leroy.nas-release-target': COMMIT}
        if ROUND is not None:
            labels['io.leroy.comparison'] = ROUND
        program = discover_program(CONTAINER, labels=labels, retained_labels=('io.leroy.engine',))
        _GUEST_PIN = json.loads(remote(program, timeout=45, sudo=True))
    program = (verify_program(_GUEST_PIN) + '\nimport base64,subprocess,sys\nargs=' + repr(args) + '\n'
               'engine=PIN["labels"]["io.leroy.engine"]\nassert engine in {"jenkins","leroy"}\n'
               'args[1:1]=["-o","ControlPath="+' + repr(REMOTE + '/.admin-') + '+engine+".sock"]\n'
               'args=["nsenter","-t",str(PIN["pid"]),"-n",*args]\n'
               + payload +
               'r=subprocess.run(args,input=data,capture_output=True,timeout=' + repr(timeout - 15) + ')\n'
               'verify_pin(PIN)\n'
               "sys.stdout.buffer.write(r.stdout)\nsys.stderr.buffer.write(r.stderr[-1800:])\nsys.exit(r.returncode)\n")
    return remote(program, timeout, sudo=True)


def wait_ready(timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            guest('test -f /var/lib/leroy-vm/ready && systemctl is-active --quiet docker', timeout=30)
            return
        except RuntimeError as error:
            if any(message in str(error).lower() for message in ('permission denied', 'host key verification failed',
                                                                'remote host identification has changed',
                                                                'controlpath too long')):
                raise
        # The unchanged host policy allows fewer than six new SSH connections
        # per 30 seconds. Slow NAS boot must not turn readiness polling into a
        # sustained UFW block (rejected probes refresh the recent-entry timer).
        time.sleep(35)
    raise TimeoutError('NAS release VM did not become ready; no CI job submitted')


def state():
    value = remote("import json,subprocess\nr=subprocess.run(['docker','inspect'," + repr(CONTAINER) +
                   "],capture_output=True,text=True,timeout=20)\nprint(json.dumps(json.loads(r.stdout)[0] if not r.returncode else None))",
                   timeout=35)
    info = json.loads(value)
    if info:
        assert info['Config']['Labels']['io.leroy.nas-release-target'] == COMMIT
        assert next(m['Source'] for m in info['Mounts'] if m['Destination'] == '/baseline') in {
            REMOTE, SSD_ROOT + '/baseline'}
        assert not next(m['RW'] for m in info['Mounts'] if m['Destination'] == '/baseline')
    return info


def disk_health():
    """Read QMP counters and the error-only trace, without guest connections."""
    code = r'''
import json,pathlib,socket
with socket.socket(socket.AF_UNIX) as connection:
 connection.settimeout(10);connection.connect('/run/qmp.sock');stream=connection.makefile('rb');stream.readline()
 def query(name):
  connection.sendall((json.dumps({'execute':name,'id':name})+'\n').encode())
  while True:
   value=json.loads(stream.readline())
   if value.get('id')==name:
    assert 'error' not in value,value
    return value['return']
 query('qmp_capabilities')
 blocks=query('query-block');stats=query('query-blockstats')
 block=next(row for row in blocks if row['device']=='virtio0')
 counters=next(row['stats'] for row in stats if row['device']=='virtio0')
 print(json.dumps({'cache':block['inserted']['cache'],'io_status':block['io-status'],
  'io_throttle':{'read_bps':block['inserted'].get('bps_rd',0),'write_bps':block['inserted'].get('bps_wr',0)},
  'counters':{k:v for k,v in counters.items() if k.startswith(('failed_','flush_'))},
  'flush_error_trace':pathlib.Path('/vm/disk-errors.trace').read_text()[-4000:]}))
'''
    program = 'import subprocess\nr=subprocess.run(["docker","exec",' + repr(CONTAINER) + \
              ',"python3","-c",' + repr(code) + \
              '],capture_output=True,text=True,timeout=20)\nassert not r.returncode,r.stderr[-1000:]\nprint(r.stdout)'
    return json.loads(remote(program, timeout=30))


def storage_probe():
    """Exercise only a disposable file in the fresh guest before original CI."""
    code = r'''
import hashlib,json,os,pathlib,time
root=pathlib.Path('/var/tmp/leroy-release-storage-probe');root.mkdir(mode=0o700)
path=root/'probe.bin';started=time.monotonic();chunk=b'\x5a'*(8*1024**2)
with path.open('xb',buffering=0) as stream:
 for _ in range(128):
  assert stream.write(chunk)==len(chunk);os.fsync(stream.fileno())
with path.open('rb') as stream:
 actual=hashlib.file_digest(stream,'sha256').hexdigest()
expected=hashlib.sha256()
for _ in range(128):expected.update(chunk)
assert actual==expected.hexdigest()
path.unlink();root.rmdir()
flags=os.statvfs('/').f_flag
assert not flags & os.ST_RDONLY
print(json.dumps({'bytes_written_and_verified':128*len(chunk),'fsync_operations':128,
 'duration_seconds':time.monotonic()-started,'root_read_only':bool(flags & os.ST_RDONLY)}))
'''
    return json.loads(guest('sudo python3 -B -', code, timeout=300))


def stop():
    info = state()
    if info and info['State']['Running']:
        guest('sudo python3 - stop', (ROOT / 'infra/vm/graphato-lifecycle.py').read_text(), timeout=300)
        remote('import subprocess\nsubprocess.run(' + repr(['docker', 'stop', '--time', '240', CONTAINER]) +
               ',check=True,capture_output=True,timeout=270)', timeout=300)
        info = state()
        assert not info['State']['Running'] and not info['State']['OOMKilled']
        disk = next(m['Source'] for m in info['Mounts'] if m['Destination'] == '/vm')
        shutdown = json.loads(remote('import pathlib\nprint(pathlib.Path(' + repr(disk + '/shutdown.json') + ').read_text())', sudo=True))
        assert not shutdown['forced'] and shutdown['qemu_exit_code'] == 0, 'Unclean guest stop; retain evidence'


def start(engine, *, resume_empty=False, postgres_init=False, memory_pressure_folder=None):
    assert engine in {'jenkins', 'leroy'}
    assert ROUND is not None, 'An explicit new comparison namespace is required'
    if memory_pressure_folder is not None:
        assert memory_pressure_folder.name == ROUND and memory_pressure_folder.is_dir()
        assert RESOURCE_PROFILE in MEMORY_PRESSURE_PROFILES
    identity = json.loads((LOCAL / 'staged.json').read_text())
    assert identity['commit'] == COMMIT and identity['snapshot'] == SNAPSHOT
    info = state()
    if info:
        assert not info['State']['Running'], 'Stop the previous owned target cleanly first'
        remote('import subprocess\nsubprocess.run(' + repr(['docker', 'rm', CONTAINER]) + ',check=True,capture_output=True)')
    if RESOURCE_PROFILE in SSD_PROFILES:
        proof = json.loads((LOCAL / 'staged-ssd.json').read_text())
        assert proof['baseline_sha256'] == identity['sha256'] and proof['baseline_root'] == BASELINE_ROOT
        if RESOURCE_PROFILE in FILE_MEMORY_PROFILES:
            from nas_vm_file_memory import require_launcher

            require_launcher(proof)
        else:
            assert proof['launcher_sha256'] == digest(ROOT / 'infra/vm/launch.py')
    if VM_IO_LIMITS:
        # SSD test storage is deliberately private. Verify its mount as root,
        # before creating any overlay; never weaken the directory permissions.
        remote('import pathlib,stat,subprocess\np=pathlib.Path(' + repr(VM_IO_LIMITS['device']) + ')\n'
               'assert stat.S_ISBLK(p.stat().st_mode)\n'
               "source=subprocess.check_output(['findmnt','-n','-T'," + repr(DISK_ROOT) + ",'-o','SOURCE'],text=True).strip()\n"
               'mount=pathlib.Path(' + repr(VM_IO_LIMITS.get('mount_device', VM_IO_LIMITS['device'])) + ')\n'
               'assert pathlib.Path(source).resolve()==mount.resolve()\n'
               'if mount!=p:\n'
               " sysfs=pathlib.Path('/sys/class/block',mount.name)\n"
               " assert (sysfs/'partition').is_file() and sysfs.resolve().parent.name==p.name\n"
               " assert not pathlib.Path('/sys/class/block',p.name,'partition').exists()\n", sudo=True)
    disk = DISK_ROOT + '/runs/' + ROUND + '/' + engine
    # No reset, recursive deletion, snapshot overwrite, or implicit repeat.
    remote('import pathlib\np=pathlib.Path(' + repr(disk) + ')\n'
           + ("assert p.is_dir() and p.resolve()==p and not p.is_symlink() and not any(p.iterdir()),'Only an explicitly inspected empty preparation directory can be resumed'\n"
              if resume_empty else
              "assert not p.exists(),'Engine overlay already exists; resume the retained run'\np.parent.mkdir(parents=True,exist_ok=True,mode=0o700)\np.mkdir(mode=0o700)\n"), sudo=True)
    args = ['docker', 'run', '-d', '--name', CONTAINER, '--label', 'io.leroy.nas-release-target=' + COMMIT,
            '--label', 'io.leroy.engine=' + engine, '--network', 'container:leroy-nas-parity-vm-access-1',
            '--label', 'io.leroy.comparison=' + ROUND,
            '--device', '/dev/kvm:/dev/kvm', '--cap-drop', 'ALL', '--cap-add', 'NET_ADMIN',
            '--security-opt', 'no-new-privileges:true', '--read-only', '--tmpfs', '/tmp:size=64m',
            '--tmpfs', '/run:size=16m', '--memory', str(CONTAINER_MEMORY_GIB) + 'g',
            '--memory-swap', str(CONTAINER_MEMORY_SWAP_GIB) + 'g', '--cpus', '6',
            '--pids-limit', '256', '--stop-timeout', '240', '--log-opt', 'max-size=10m',
            '--log-opt', 'max-file=3', '--log-opt', 'mode=non-blocking', '--log-opt', 'max-buffer-size=4m',
            '-e', 'VM_MEMORY_MB=' + str(GUEST_MEMORY_MB),
            '-e', 'VM_DISK_CACHE=' + DISK_CACHE, '-e', 'VM_CPUS=6', '-e', 'VM_SSH_PORT=12225',
            '-e', 'VM_MIN_HOST_SWAP_MB=' + str(MIN_HOST_SWAP_MB),
            '-e', 'VM_MIN_HOST_AVAILABLE_MB=' + str(MIN_HOST_AVAILABLE_MB),
            '-e', 'VM_MIN_DISK_FREE_MB=' + str(MIN_DISK_FREE_MB),
            '--mount', 'type=bind,source=' + BASELINE_ROOT + ',target=/baseline,readonly',
            '--mount', 'type=bind,source=' + disk + ',target=/vm',
            '--mount', 'type=bind,source=' + REMOTE + ',target=/config,readonly',
            '--mount', 'type=bind,source=' + LAUNCHER + ',target=/opt/leroy-vm/launch.py,readonly',
            '--entrypoint', 'sh', identity['qemu_image_id'], '-c',
            'for destination in 87.106.133.233/32 213.165.73.233/32; do '
            'iptables -C OUTPUT -d "$destination" -j REJECT 2>/dev/null || '
            'iptables -A OUTPUT -d "$destination" -j REJECT || exit 1; done; '
            'exec python3 /opt/leroy-vm/launch.py']
    if VM_IO_LIMITS and VM_IO_LIMITS.get('target') != 'qemu-disk':
        # Only throttle the owned VM. Do not change the host scheduler or any
        # other container's durability, memory, or I/O configuration.
        args[2:2] = ['--device-read-bps', f"{VM_IO_LIMITS['device']}:{VM_IO_LIMITS['read_bps']}",
                     '--device-write-bps', f"{VM_IO_LIMITS['device']}:{VM_IO_LIMITS['write_bps']}"]
    if RESOURCE_PROFILE in FILE_MEMORY_PROFILES:
        from nas_vm_file_memory import prepare_memory_file

        memory = prepare_memory_file(engine)
        args[2:2] = ['-e', 'VM_MEMORY_FILE=/vm-memory/ram.bin', '--mount',
                     'type=bind,source=' + memory['directory'] + ',target=/vm-memory']
    if RESOURCE_PROFILE in PROTECTED_FILE_MEMORY_PROFILES:
        args[2:2] = ['--cgroup-parent=-.slice', '--memory-reservation', '4g']
    if RESOURCE_PROFILE == DISK_QOS_FILE_MEMORY_PROFILE:
        args[2:2] = ['-e', 'VM_DISK_READ_BPS=134217728', '-e', 'VM_DISK_WRITE_BPS=33554432']
    remote('import subprocess\nsubprocess.run(' + repr(args) + ',check=True,capture_output=True,timeout=90)', timeout=120)
    if memory_pressure_folder is not None:
        from nas_vm_memory_pressure import apply_outer_memory_pressure

        apply_outer_memory_pressure(memory_pressure_folder, engine)
    global _GUEST_PIN
    _GUEST_PIN = None
    wait_ready()
    if postgres_init:
        from nas_vm_postgres_init import PROGRAM

        guest('sudo python3 -B -', PROGRAM, timeout=60)
    guest('sudo python3 - start', (ROOT / 'infra/vm/graphato-lifecycle.py').read_text(), timeout=300)
    if RESOURCE_PROFILE in GUEST_SWAP_PROFILES:
        from nas_vm_guest_swap import apply_guest_swap

        assert memory_pressure_folder is not None, 'Retained environment proof required for this candidate'
        apply_guest_swap(memory_pressure_folder, engine)
    return state()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['stage', 'stage-ssd', 'state', 'stop'])
    args = parser.parse_args()
    if args.action == 'stage':
        print(json.dumps(stage()))
    elif args.action == 'stage-ssd':
        stage_ssd()
    elif args.action == 'stop':
        stop()
    else:
        info = state()
        print(json.dumps(None if info is None else {'state': info['State'], 'resources': {
            key: info['HostConfig'][key] for key in ('Memory', 'MemorySwap', 'NanoCpus')},
            'engine': info['Config']['Labels']['io.leroy.engine']}))


if __name__ == '__main__':
    try:
        main()
    except subprocess.TimeoutExpired:
        raise SystemExit('SSH operation timed out; retain state and resume without redispatch') from None
