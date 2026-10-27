"""Byte-verify one closed overnight test disk on HDD before freeing its SSD copy."""

import argparse
import json

import nas_release_vm as vm
from nas_followup_support import production_jobs
from nas_gitea_target import idle

PROGRAM = r'''
import hashlib,json,os,pathlib,shutil,subprocess,time,xml.etree.ElementTree as ET
owner=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (owner/'.leroy-owned').is_file()
ssd=pathlib.Path('/overlay/leroy-nas-parity-release-test/0ad540dd5780')
source=ssd/'runs'/ROUND/ENGINE/'system.qcow2'
dest=owner/'release-vm/0ad540dd5780/archived-night-20261014'/ROUND/ENGINE
assert source.resolve(strict=True)==source and not source.is_symlink() and not dest.exists()
assert json.loads((source.parent/'prepared.json').read_text())['commit']==COMMIT
assert (source.parent/'shutdown.json').is_file()
guard=owner/WINDOW
native=json.loads(subprocess.check_output(['docker','inspect','jenkins'],text=True))[0]
home=pathlib.Path(next(m['Source'] for m in native['Mounts'] if m['Destination']=='/var/jenkins_home')).resolve(strict=True)
last=0
def checkpoint(force=False):
 global last
 if not force and time.monotonic()-last<15:return
 state=json.loads((guard/'state.json').read_text())
 assert state['phase']=='paused' and time.time()<state['deadline']-state['restore_margin_seconds']-600
 info=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-release-target-vm'],text=True,timeout=20))[0]
 assert not info['State']['Running'] and info['Config']['Labels']['io.leroy.nas-release-target']==COMMIT
 for name,row in EXPECTED.items():
  job=(home/'jobs'/name).resolve(strict=True);assert job.is_relative_to(home/'jobs')
  number=int((job/'nextBuildNumber').read_text())-1 if (job/'nextBuildNumber').is_file() else 0
  assert number==row['number']
  if number:assert ET.parse(job/'builds'/str(number)/'build.xml').getroot().findtext('completed')=='true'
 last=time.monotonic()
checkpoint(True);stat=source.stat()
assert shutil.disk_usage(owner/'release-vm/0ad540dd5780').free>stat.st_size+100*1024**3
dest.mkdir(parents=True,mode=0o700);target=dest/'system.qcow2';os.nice(15)
value={'started_at':time.time(),'round':ROUND,'engine':ENGINE,'source':str(source),'archive':str(target),'source_removed':False}
def save():
 p=dest/'archive-progress.json';p.write_text(json.dumps(value,indent=2)+'\n');p.chmod(0o600)
save()
def read_copy(copy):
 digest=hashlib.sha256();processed=0;start=time.monotonic()
 with (source if copy else target).open('rb') as src:
  out=target.open('xb') if copy else None
  try:
   while block:=src.read(8*1024**2):
    checkpoint();digest.update(block)
    if out:
     if block.count(0)==len(block):out.seek(len(block),1)
     else:out.write(block)
    processed+=len(block)
    if out and processed%(64*1024**2)==0:
     out.flush();os.fdatasync(out.fileno());os.posix_fadvise(out.fileno(),processed-64*1024**2,64*1024**2,os.POSIX_FADV_DONTNEED)
    os.posix_fadvise(src.fileno(),processed-len(block),len(block),os.POSIX_FADV_DONTNEED)
    delay=processed/(64*1024**2)-(time.monotonic()-start)
    if delay>0:time.sleep(delay)
   if out:out.truncate(stat.st_size);out.flush();os.fsync(out.fileno())
  finally:
   if out:out.close()
 return digest.hexdigest()
first=read_copy(True);value.update(copy_sha256=first,copy_finished_at=time.time());save()
second=read_copy(False);assert first==second and target.stat().st_size==stat.st_size
assert (source.stat().st_size,source.stat().st_mtime_ns)==(stat.st_size,stat.st_mtime_ns)
shutil.copystat(source,target,follow_symlinks=False);os.chown(target,stat.st_uid,stat.st_gid)
for p in source.parent.iterdir():
 if p==source or not p.is_file():continue
 assert not p.is_symlink() and p.stat().st_size<8*1024**2;shutil.copy2(p,dest/p.name)
value.update(sha256=second,bytes=stat.st_size,verified_at=time.time());save()
fd=os.open(dest,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
pointer=source.parent/'archived-system-disk.json';assert not pointer.exists()
with pointer.open('x') as f:f.write(json.dumps(value,indent=2)+'\n');f.flush();os.fsync(f.fileno())
pointer.chmod(0o600);checkpoint(True)
assert source.resolve(strict=True)==source and target.is_file()
source.unlink();fd=os.open(source.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
value.update(source_removed=True,finished_at=time.time(),ssd_free_bytes=shutil.disk_usage(ssd).free);save()
print(json.dumps(value))
'''


def main():
    from run_nas_night_window import BASE, WINDOW, require_approval

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--round', choices=('night-rust-leroy-20261014', 'night-rust-jenkins-20261014',
                                           'night-release-20261014', 'original-night-rust-leroy-20261014',
                                           'original-night-rust-jenkins-20261014', 'original-night-release-20261014',
                                           'original-night-b-rust-leroy-20261014', 'original-night-b-rust-jenkins-20261014',
                                           'original-night-b-release-20261014', 'original-night-c-rust-leroy-20261014',
                                           'original-night-c-rust-jenkins-20261014', 'original-night-c-release-20261014',
                                           'original-night-d-rust-leroy-20261014', 'original-night-d-rust-jenkins-20261014',
                                           'original-night-d-release-20261014', 'original-night-e-release-20261014'), required=True)
    parser.add_argument('--engine', choices=('jenkins', 'leroy'), required=True)
    parser.add_argument('--resource-window', choices=('resource-window-night-20261014',
                                                    'resource-window-original-night-20261014',
                                                    'resource-window-original-night-20261014-b',
                                                    'resource-window-original-night-20261014-c',
                                                    'resource-window-original-night-20261014-d',
                                                    'resource-window-original-night-20261014-e',
                                                    'resource-window-original-night-20261014-f'),
                        default='resource-window-night-20261014')
    args = parser.parse_args()
    if args.resource_window.startswith('resource-window-original-night-20261014'):
        import run_nas_original_night_window as original

        original.configure_attempt(args.resource_window.rsplit('-', 1)[-1] if args.resource_window.rsplit('-', 1)[-1] in {'b', 'c', 'd', 'e', 'f'} else 'a')
        BASE, WINDOW, require_approval = original.BASE, original.WINDOW, original.require_approval

    require_approval()
    assert args.resource_window == WINDOW
    suffix = WINDOW.rsplit('-', 1)[-1]
    prefix = ('original-night-' + suffix + '-' if suffix in {'b', 'c', 'd', 'e', 'f'} else 'original-night-') if 'original-night-' in WINDOW else 'night-'
    if suffix == 'f':
        prefix = 'original-night-e-'
        assert args.round == 'original-night-e-release-20261014'
    assert args.round.startswith(prefix)
    if args.round.startswith('night-rust-'):
        assert args.round == 'night-rust-' + args.engine + '-20261014'
    if args.round.startswith('original-night-rust-'):
        assert args.round == 'original-night-rust-' + args.engine + '-20261014'
    if args.round.startswith('original-night-b-rust-'):
        assert args.round == 'original-night-b-rust-' + args.engine + '-20261014'
    if args.round.startswith('original-night-c-rust-'):
        assert args.round == 'original-night-c-rust-' + args.engine + '-20261014'
    if args.round.startswith('original-night-d-rust-'):
        assert args.round == 'original-night-d-rust-' + args.engine + '-20261014'
    idle()
    before = production_jobs()
    assert not before['active_builds'] and before['older_concurrent_build_history_verified']
    marker = BASE / WINDOW / ('archive-' + args.round + '-' + args.engine + '.json')
    assert not marker.exists()
    constants = {'ROUND': args.round, 'ENGINE': args.engine, 'COMMIT': vm.COMMIT,
                 'WINDOW': WINDOW, 'EXPECTED': before['jobs']}
    program = ''.join(name + '=' + repr(value) + '\n' for name, value in constants.items()) + PROGRAM
    proof = json.loads(vm.remote(program, sudo=True, timeout=2400))
    marker.write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
