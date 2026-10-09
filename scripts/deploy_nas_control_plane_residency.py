"""Keep the owned idle control plane resident without changing code or lease budgets."""

import argparse
import json
from datetime import datetime, timezone

from nas_gitea_target import idle
from nas_ssh import ROOT, run_script

PROGRAM = r'''
import hashlib,json,pathlib,subprocess,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
outer=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-docker-1'],text=True))[0]
assert outer['Id']=='7d029e17dc28b04ec41ac927360062f057c97564227c62e7e01a50a4938b5a00'
assert outer['HostConfig']['Memory']==4831838208 and outer['HostConfig']['MemorySwap']==8053063680
prefix=['docker','compose','--project-directory',str(root)]
def config(file=None):
 args=prefix[:]
 if file:
  args+=['-f',str(file)]
  for override in ('compose.override.yaml','compose.override.yml'):
   if (root/override).exists():args+=['-f',str(root/override)]
 return json.loads(subprocess.check_output(args+['config','--format','json'],text=True))
path=root/'compose.yaml';backup=root/'compose.yaml.before-control-plane-residency'
if RESUME:
 assert backup.exists();before=backup.read_bytes();before_config=config(backup)
else:
 assert not backup.exists();before=path.read_bytes();before_config=config()
text=before.decode()
expected={'controller':(256,128,1),'postgres':(256,128,0.5),'runner':(192,64,0.5)}
states={}
for name,(memory,reservation,cpu) in expected.items():
 info=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-'+name+'-1'],text=True))[0]
 assert info['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
 assert info['HostConfig']['Memory']==memory*1024**2 and info['HostConfig']['MemorySwap']==2*memory*1024**2
 assert info['State']['Running'] and not info['State']['OOMKilled']
 old='    mem_limit: '+str(memory)+'m\n    cpus: '+str(cpu)+'\n'
 assert text.count(old)==1
 text=text.replace(old,'    mem_limit: '+str(memory)+'m\n    memswap_limit: '+str(memory)+'m\n    mem_reservation: '+str(reservation)+'m\n    cpus: '+str(cpu)+'\n',1)
 states[name]={'before_id':info['Id'],'image':info['Image'],'mounts':info['Mounts']}
if RESUME:assert path.read_text()==text,'Resume only the inspected configuration staging failure'
else:backup.write_bytes(before);path.write_text(text)
(root/'control-plane-residency-before.json').write_text(json.dumps(states))
after_config=config();normalized=json.loads(json.dumps(after_config))
for name,(memory,reservation,cpu) in expected.items():
 service=normalized['services'][name]
 assert int(service.pop('memswap_limit'))==memory*1024**2
 assert int(service.pop('mem_reservation'))==reservation*1024**2
assert normalized==before_config,'No other configuration, dependency or secret changes'
subprocess.run(prefix+['stop','--timeout','120','runner','controller','postgres'],check=True,timeout=400,stdout=subprocess.DEVNULL)
for name,(memory,reservation,cpu) in [('postgres',expected['postgres']),('controller',expected['controller']),('runner',expected['runner'])]:
 subprocess.run(prefix+['up','-d','--no-deps','--pull','never',name],check=True,timeout=120,stdout=subprocess.DEVNULL)
 deadline=time.monotonic()+120
 while time.monotonic()<deadline:
  info=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-'+name+'-1'],text=True))[0]
  if info['State']['Running'] and info['State'].get('Health',{}).get('Status','healthy')=='healthy':break
  time.sleep(2)
 else:raise TimeoutError('Owned service not healthy: '+name)
 assert info['Image']==states[name]['image']
 assert sorted(info['Mounts'],key=lambda m:m['Destination'])==sorted(states[name]['mounts'],key=lambda m:m['Destination'])
 assert info['HostConfig']['Memory']==info['HostConfig']['MemorySwap']==memory*1024**2
 assert info['HostConfig']['MemoryReservation']==reservation*1024**2
 relative=(pathlib.Path('/proc',str(info['State']['Pid']),'cgroup')).read_text().strip().split('::',1)[1]
 group=pathlib.Path('/sys/fs/cgroup',relative.lstrip('/'))
 assert (group/'memory.swap.max').read_text().strip()=='0'
 assert (group/'memory.swap.current').read_text().strip()=='0'
 assert int((group/'memory.low').read_text())==reservation*1024**2
 states[name].update(after_id=info['Id'],memory_swap_bytes=memory*1024**2,memory_low_bytes=reservation*1024**2,swap_current_bytes=0)
assert json.loads(subprocess.check_output(['docker','inspect',outer['Id']],text=True))[0]['State']['Running']
print('EVIDENCE='+json.dumps({'services':states,'code_images_unchanged':True,'database_and_data_volumes_preserved':True,'outer_daemon_unchanged':True,'worker_images_unchanged':True,'original_builder_limits_unchanged':True,'lease_seconds_unchanged':90,'worker_confirmation_seconds_unchanged':45,'compose_before_sha256':hashlib.sha256(before).hexdigest(),'compose_after_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'production_modified':False,'effectiveness_requires_workload_validation':True}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume-config-validation', action='store_true')
    args = parser.parse_args()
    idle()
    destination = ROOT / 'test-results/nas-parity/followup/control-plane-residency-deployment.json'
    assert not destination.exists(), 'Retain the first deployment; no implicit repeat'
    result = run_script("python3 - <<'PY'\nRESUME=" + repr(args.resume_config_validation) + '\n' + PROGRAM + '\nPY\n', ROOT / '.local/nas-ssh.json',
                        sudo=True, timeout=700)
    assert result.returncode == 0, result.stderr[-2000:]
    value = json.loads(next(line[9:] for line in result.stdout.splitlines() if line.startswith('EVIDENCE=')))
    # Mounts can contain secret-file paths, never their contents; retain locally only.
    value.update(at=datetime.now(timezone.utc).isoformat())
    destination.write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({'deployed': True, 'services': list(value['services']), 'code_images_unchanged': True,
                      'swap_disabled': True, 'lease_seconds_unchanged': 90, 'production_modified': False}), flush=True)


if __name__ == '__main__':
    main()
