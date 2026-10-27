"""Inventory a retained original worker image after its CI run has completed.

The owned test VM may boot for this read-only image audit; application services
remain stopped. No CI job, image process, source edit, or fixture retry occurs.
"""

import argparse
import base64
import gzip
import hashlib
import json

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT

PROGRAM = r'''
import base64,gzip,hashlib,json,os,pathlib,re,resource,subprocess,tempfile,time
assert os.geteuid()==0 and pathlib.Path('/var/lib/leroy-vm/ready').is_file()
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip()=='kvm'
ids=subprocess.check_output(['docker','ps','-q'],text=True).split()
running=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True,timeout=15)) if ids else []
assert {c['Name'] for c in running}<={'/leroy-acme-directory','/leroy-acme-pebble'},'Application and original CI fixtures must remain stopped'
assert re.fullmatch('[a-f0-9]{40}',COMMIT)
tag='graphato/server-tests:git-'+COMMIT
image=json.loads(subprocess.check_output(['docker','image','inspect',tag],text=True,timeout=15))[0]
assert image['Os']=='linux' and image['Architecture']=='amd64'
assert not image['Config'].get('Volumes'),'Declared anonymous volumes would obscure image files'
name='leroy-image-audit-'+ENGINE
prior=subprocess.run(['docker','inspect',name],capture_output=True,text=True,timeout=15)
assert prior.returncode!=0,'Inspect an uncertain prior audit before reusing its name'
identity=subprocess.check_output(['docker','create','--name',name,'--label','io.leroy.image-audit='+COMMIT,
 '--network','none','--hostname','leroy-image-audit','--read-only','--cap-drop','ALL',
 '--memory','64m','--memory-swap','64m','--cpus','0.25','--pids-limit','16',
 '--entrypoint','/bin/false',image['Id']],text=True,timeout=30).strip()
assert re.fullmatch('[a-f0-9]{64}',identity)
started=time.monotonic();export=None;original_limit=resource.getrlimit(resource.RLIMIT_AS)
try:
 c=json.loads(subprocess.check_output(['docker','inspect',identity],text=True,timeout=15))[0]
 assert not c['State']['Running'] and not c['Mounts'] and c['Image']==image['Id']
 with tempfile.TemporaryFile() as errors:
  export=subprocess.Popen(['docker','export',identity],stdout=subprocess.PIPE,stderr=errors)
  # Apply only to Python after launching Go, avoiding Go's large virtual arena.
  resource.setrlimit(resource.RLIMIT_AS,(384*1024**2,original_limit[1]));os.nice(15)
  class Reader:
   def __init__(self,stream):self.stream=stream;self.count=0;self.started=time.monotonic();self.checked=self.started;self.relief=0
   def read(self,size):
    data=self.stream.read(size);self.count+=len(data)
    delay=self.count/(16*1024**2)-(time.monotonic()-self.started)
    if delay>0:time.sleep(delay)
    if time.monotonic()-self.checked>=10:
     self.checked=time.monotonic()
     memory={l.split(':')[0]:int(l.split()[1]) for l in pathlib.Path('/proc/meminfo').read_text().splitlines() if l.startswith(('MemAvailable:','Cached:'))}
     if memory['MemAvailable']>=1024*1024 and memory['Cached']>=768*1024:
      pathlib.Path('/proc/sys/vm/drop_caches').write_text('1\n');self.relief+=1
    return data
  reader=Reader(export.stdout);value=inventory(reader);value['audit_only_guest_clean_cache_relief_count']=reader.relief
  # Consume the tar trailer and verify the exporting daemon completed cleanly.
  while export.stdout.read(1024**2):
   assert time.monotonic()-started<1250
  assert export.wait(timeout=30)==0,'Image export failed; no equivalence evidence'
 resource.setrlimit(resource.RLIMIT_AS,original_limit)
 value.update(image_id=image['Id'],ordered_rootfs=image['RootFS']['Layers'],
  execution_config_sha256=hashlib.sha256(json.dumps(image['Config'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),
  duration_seconds=time.monotonic()-started,image_process_started=False,
  application_services_running_during_inventory=False,original_ci_redispatched=False)
 data=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
 print(json.dumps({'inventory_sha256':hashlib.sha256(data).hexdigest(),
  'gzip_base64':base64.b64encode(gzip.compress(data)).decode()}))
finally:
 resource.setrlimit(resource.RLIMIT_AS,original_limit)
 if export is not None and export.poll() is None:
  export.terminate()
  try:export.wait(timeout=10)
  except subprocess.TimeoutExpired:export.kill();export.wait(timeout=10)
 c=json.loads(subprocess.check_output(['docker','inspect',identity],text=True,timeout=15))[0]
 assert not c['State']['Running'] and c['Config']['Labels']['io.leroy.image-audit']==COMMIT
 subprocess.run(['docker','rm',identity],check=True,capture_output=True,timeout=30)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', required=True)
    parser.add_argument('--engine', choices=('leroy', 'jenkins'), required=True)
    args = parser.parse_args()
    folder = (ROOT / args.folder).resolve()
    assert folder.is_relative_to(ROOT / 'test-results/nas-parity/followup')
    final = json.loads((folder / 'final-state.json').read_text())
    assert final['original_ci_terminal'] and not final['vm_running']
    prepared = json.loads((folder / 'prepared.json').read_text())
    assert prepared['commit'] == vm.COMMIT
    vm.configure(folder.name, prepared['resource_profile'])
    result = folder / (args.engine + '-worker-filesystem.json')
    assert not result.exists(), 'Retain the completed image inventory'
    idle()
    info = vm.state()
    assert not info['State']['Running'] and info['Config']['Labels']['io.leroy.comparison'] == folder.name
    assert info['Config']['Labels']['io.leroy.engine'] == args.engine
    before = begin(folder, args.engine + '-image-audit')
    marker = folder / (args.engine + '-image-audit-start.json')
    assert not marker.exists(), 'Inspect an incomplete audit before resuming'
    marker.write_text(json.dumps({'production_guard_before': before, 'ci_run_restarted': False}) + '\n')
    vm.remote('import subprocess\nsubprocess.run(' + repr(['docker', 'start', vm.CONTAINER]) +
              ',check=True,capture_output=True,timeout=30)')
    source = (ROOT / 'scripts/nas_image_filesystem.py').read_text()
    code = source + '\nCOMMIT=' + repr(vm.COMMIT) + '\nENGINE=' + repr(args.engine) + '\n' + PROGRAM
    try:
        vm.wait_ready()
        # A normal guest shutdown can preserve Docker restart policies. Stop
        # the owned baseline before reading the image; never redispatch CI.
        vm.guest('sudo python3 - stop', (ROOT / 'infra/vm/graphato-lifecycle.py').read_text(), timeout=240)
        packet = json.loads(vm.guest('sudo python3 -B -', code, timeout=1380))
        data = gzip.decompress(base64.b64decode(packet['gzip_base64']))
        assert hashlib.sha256(data).hexdigest() == packet['inventory_sha256']
        result.write_bytes(data)
    finally:
        vm.stop()
        finish(folder, args.engine + '-image-audit', before)
    value = json.loads(data)
    print(json.dumps({k: value[k] for k in ('image_id', 'entry_count', 'file_bytes_hashed', 'filesystem_sha256', 'duration_seconds')}))


if __name__ == '__main__':
    main()
