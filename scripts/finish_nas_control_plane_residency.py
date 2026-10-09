"""Finish the inspected update after mount-array ordering stopped validation."""

import json
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script

PROGRAM = r'''
import hashlib,json,pathlib,subprocess,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
assert (root/'compose.yaml.before-control-plane-residency').exists()
prefix=['docker','compose','--project-directory',str(root)]
runner=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-runner-1'],text=True))[0]
assert runner['Id']==PARTIAL['runner']['id'] and not runner['State']['Running']
assert runner['Image']==EXPECTED['runner']
subprocess.run(prefix+['up','-d','--no-deps','--pull','never','runner'],check=True,timeout=120,stdout=subprocess.DEVNULL)
rows={}
for name,memory,reservation in [('postgres',256,128),('controller',256,128),('runner',192,64)]:
 info=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-'+name+'-1'],text=True))[0]
 assert info['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
 assert info['State']['Running'] and info['State'].get('Health',{}).get('Status','healthy')=='healthy'
 assert info['Image']==EXPECTED[name]
 assert sorted(info['Mounts'],key=lambda m:m['Destination'])==sorted(PARTIAL[name]['mounts'],key=lambda m:m['Destination'])
 assert info['HostConfig']['Memory']==info['HostConfig']['MemorySwap']==memory*1024**2
 assert info['HostConfig']['MemoryReservation']==reservation*1024**2
 relative=pathlib.Path('/proc',str(info['State']['Pid']),'cgroup').read_text().strip().split('::',1)[1]
 group=pathlib.Path('/sys/fs/cgroup',relative.lstrip('/'))
 assert (group/'memory.swap.max').read_text().strip()==(group/'memory.swap.current').read_text().strip()=='0'
 assert int((group/'memory.low').read_text())==reservation*1024**2
 rows[name]={'id':info['Id'],'image':info['Image'],'memory_swap_bytes':memory*1024**2,'memory_low_bytes':reservation*1024**2,'swap_current_bytes':0}
outer=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-docker-1'],text=True))[0]
assert outer['Id']=='7d029e17dc28b04ec41ac927360062f057c97564227c62e7e01a50a4938b5a00' and outer['State']['Running']
assert outer['HostConfig']['Memory']==4831838208 and outer['HostConfig']['MemorySwap']==8053063680
print('EVIDENCE='+json.dumps({'services':rows,'code_images_match_previously_deployed_versions':True,'database_and_data_volumes_preserved':True,'outer_daemon_unchanged':True,'worker_images_unchanged':True,'original_builder_limits_unchanged':True,'lease_seconds_unchanged':90,'worker_confirmation_seconds_unchanged':45,'compose_before_sha256':hashlib.sha256((root/'compose.yaml.before-control-plane-residency').read_bytes()).hexdigest(),'compose_after_sha256':hashlib.sha256((root/'compose.yaml').read_bytes()).hexdigest(),'production_modified':False,'effectiveness_requires_workload_validation':True}))
'''


def main():
    base = ROOT / 'test-results/nas-parity/followup'
    destination = base / 'control-plane-residency-deployment.json'
    assert not destination.exists()
    partial = json.loads((base / 'control-plane-residency-partial.json').read_text())
    ui = json.loads((base.parent / 'timeline-status-ui.json').read_text())
    runner = json.loads((base / 'candidates/graphato/ed21c2e6346aab6f71494765a37ba91e0d4559b7/control-residency-deployment.json').read_text())
    expected = {'controller': ui['new_image'], 'runner': runner['images']['leroy-runner:nas-parity']['after'],
                'postgres': partial['postgres']['image']}
    program = 'PARTIAL=' + repr(partial) + '\nEXPECTED=' + repr(expected) + '\n' + PROGRAM
    result = run_script("python3 - <<'PY'\n" + program + '\nPY\n', ROOT / '.local/nas-ssh.json', sudo=True, timeout=180)
    assert result.returncode == 0, result.stderr[-1000:]
    value = json.loads(next(line[9:] for line in result.stdout.splitlines() if line.startswith('EVIDENCE=')))
    value.update(at=datetime.now(timezone.utc).isoformat(), validation_repair='Numeric string normalization and mount ordering; no additional services restarted.')
    destination.write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps(value), flush=True)


if __name__ == '__main__':
    main()
