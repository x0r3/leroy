"""Retain byte-verified, offline test disks on HDD before another SSD comparison.

Only explicitly named original attempts are archived. All source disks remain
until every copy has been verified. Production activity aborts preparation;
an incomplete outcome must be inspected before resuming.
"""

import argparse
import json
from contextlib import closing
from datetime import datetime, timezone

import nas_release_vm as vm
from compare_nas_antares import client
from nas_followup_support import inner
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT

PROGRAM = r'''
import hashlib,json,os,pathlib,re,shutil,stat,subprocess,time,xml.etree.ElementTree as ET
ssd=pathlib.Path('/overlay/leroy-nas-parity-release-test/0ad540dd5780')
hdd=pathlib.Path('/volume1/docker/leroy-nas-parity/release-vm/0ad540dd5780')
assert ssd.resolve()==ssd and hdd.resolve()==hdd
assert (ssd.parent/'.leroy-owned').is_file()
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
destination=hdd/'archived-ssd-20261011'
assert not destination.exists(), 'Inspect a previous archive before resuming'
target=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-release-target-vm']))[0]
assert target['Config']['Labels']['io.leroy.nas-release-target']=='0ad540dd578033d45e4d0c25d89fbe57b32102a4'
assert not target['State']['Running']
production=json.loads(subprocess.check_output(['docker','inspect','jenkins']))[0]
home=pathlib.Path(next(m['Source'] for m in production['Mounts'] if m['Destination']=='/var/jenkins_home')).resolve(strict=True)
last_check=0
def checkpoint(force=False):
 global last_check
 if not force and time.monotonic()-last_check<15:return
 for name,expected in EXPECTED.items():
  assert re.fullmatch('[a-zA-Z0-9_./-]+',name) and '..' not in pathlib.PurePosixPath(name).parts
  job=(home/'jobs'/name).resolve(strict=True);assert job.is_relative_to(home/'jobs')
  count=int((job/'nextBuildNumber').read_text())-1 if (job/'nextBuildNumber').is_file() else 0
  assert count==expected['number'], 'Production build counter changed; keep original disks'
  if count:
   record=job/'builds'/str(count)/'build.xml'
   assert record.resolve().is_relative_to(job) and record.stat().st_size<16*1024**2
   tree=ET.parse(record).getroot()
   assert tree.tag=='flow-build' and tree.findtext('completed')=='true', 'Production is active; keep original disks'
 last_check=time.monotonic()
checkpoint(True)
sources=[]
for namespace in ('full-release-nas-20261011-g','full-release-nas-20261011-h'):
 for engine in ('jenkins','leroy'):
  path=ssd/'runs'/namespace/engine/'system.qcow2'
  assert path.resolve(strict=True)==path and path.is_file() and not path.is_symlink()
  assert json.loads((path.parent/'prepared.json').read_text())['commit']=='0ad540dd578033d45e4d0c25d89fbe57b32102a4'
  info=path.stat()
  sources.append((path,{'namespace':namespace,'engine':engine,'size':info.st_size,'mtime_ns':info.st_mtime_ns,
   'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode),'allocated_bytes':info.st_blocks*512}))
total=sum(info['size'] for _,info in sources)
assert total<80*1024**3 and shutil.disk_usage(hdd).free>=total+100*1024**3
destination.mkdir(mode=0o700)
(destination/'.leroy-owned').write_text('Leroy retained offline SSD release disks only\n')
(destination/'.leroy-owned').chmod(0o600)
state={'started_at':time.time(),'production_modified':False,'source_disks_removed':False,
 'original_ci_evidence_replaced':False,'ssd_free_before_bytes':shutil.disk_usage(ssd).free,'disks':[]}
def record(phase):
 state['phase']=phase
 temporary=destination/'progress.json.tmp';path=destination/'progress.json'
 with temporary.open('w') as stream:
  stream.write(json.dumps(state,indent=2)+'\n');stream.flush();os.fsync(stream.fileno())
 temporary.chmod(0o600);temporary.replace(path)
 fd=os.open(destination,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
record('owned-offline-disks-validated')
os.nice(10)
def digest(path):
 result=hashlib.sha256()
 with path.open('rb') as stream:
  while block:=stream.read(8*1024**2):checkpoint();result.update(block)
 return result.hexdigest()
for source,info in sources:
 checkpoint(True)
 copied=destination/info['namespace']/info['engine']/'system.qcow2'
 copied.parent.mkdir(parents=True,mode=0o700)
 copied.parent.parent.chmod(0o700)
 start=time.monotonic();processed=0
 with source.open('rb') as input_file,copied.open('xb') as output_file:
  while block:=input_file.read(8*1024**2):
   checkpoint()
   # Preserve sparse zero regions without changing any logical disk bytes.
   if block.count(0)==len(block):output_file.seek(len(block),1)
   else:output_file.write(block)
   processed+=len(block)
   remaining=processed/(64*1024**2)-(time.monotonic()-start)
   if remaining>0:time.sleep(remaining)
  output_file.truncate(info['size']);output_file.flush();os.fsync(output_file.fileno())
 shutil.copystat(source,copied,follow_symlinks=False)
 os.chown(copied,info['uid'],info['gid'])
 original_sha=digest(source);copy_sha=digest(copied)
 assert original_sha==copy_sha and copied.stat().st_size==info['size']
 assert (source.stat().st_size,source.stat().st_mtime_ns)==(info['size'],info['mtime_ns'])
 actual=copied.stat()
 assert (actual.st_uid,actual.st_gid,stat.S_IMODE(actual.st_mode))==(info['uid'],info['gid'],info['mode'])
 fd=os.open(copied,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
 for directory in (copied.parent,copied.parent.parent):
  fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(fd)
  finally:os.close(fd)
 state['disks'].append({**info,'original_path':str(source),'archive_path':str(copied),'sha256':copy_sha,
  'bytes_and_ownership_verified':True})
 record('verified-'+info['namespace']+'-'+info['engine'])
checkpoint(True)
assert len(state['disks'])==4
# No recursive delete or broad Docker pruning: remove only the four verified
# regular source disk files. Their diagnostics and small metadata stay on SSD.
for row in state['disks']:
 source=pathlib.Path(row['original_path']);copied=pathlib.Path(row['archive_path'])
 assert source.resolve(strict=True)==source and source.is_relative_to(ssd/'runs')
 assert copied.resolve(strict=True)==copied and copied.is_relative_to(destination)
 assert (source.stat().st_size,source.stat().st_mtime_ns)==(row['size'],row['mtime_ns'])
 pointer=source.parent/'archived-system-disk.json';assert not pointer.exists()
 with pointer.open('x') as stream:
  stream.write(json.dumps(row,indent=2)+'\n');stream.flush();os.fsync(stream.fileno())
 pointer.chmod(0o600)
 source.unlink()
 fd=os.open(source.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
state.update(source_disks_removed=True,ssd_free_after_bytes=shutil.disk_usage(ssd).free,
 completed_at=time.time(),all_original_disks_retained_in_archive=True)
record('completed')
print(json.dumps(state))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    assert parser.parse_args().apply, 'Pass --apply only after all original jobs and the target VM have ended'
    folder = ROOT / 'test-results/nas-parity/followup/overlay-archive-20261011'
    folder.mkdir(parents=True, exist_ok=True)
    assert not (folder / 'started.json').exists(), 'Inspect an uncertain previous outcome before retrying'
    assert not vm.state()['State']['Running']
    assert inner('inspect', 'jenkins-parity', '--format', '{{.State.Running}}').strip() == 'false'
    with closing(client()) as api:
        for status in ('queued', 'running', 'waiting'):
            reply = api.get('/api/runs', params={'status': status})
            reply.raise_for_status()
            assert not reply.json()
        reply = api.get('/api/pipelines')
        reply.raise_for_status()
        assert not any(row['enabled'] for row in reply.json())
    before = begin(folder, 'overlay-archive')
    (folder / 'started.json').write_text(json.dumps({'at': datetime.now(timezone.utc).isoformat(),
                                                   'production_guard_before': before}) + '\n')
    expected = json.loads((folder / before).read_text())['jobs']
    proof = json.loads(vm.remote('EXPECTED=' + repr(expected) + '\n' + PROGRAM, sudo=True, timeout=2400))
    (folder / 'archive-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    finish(folder, 'overlay-archive', before)
    print(json.dumps({'original_disks_retained': True, 'verified_disks': len(proof['disks']),
                      'ssd_free_bytes': proof['ssd_free_after_bytes'], 'production_modified': False}))


if __name__ == '__main__':
    main()
