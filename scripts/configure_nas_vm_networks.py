"""Keep disposable guest Docker networks away from the Windows SSH source address."""

import argparse
import json
import re
from datetime import datetime, timezone

from nas_ssh import ROOT
from prepare_nas_vm import guest

PROGRAM = r"""
import hashlib,ipaddress,json,pathlib,subprocess,time
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip()=='kvm'
current=pathlib.Path('/opt/graphato/current')
if CANDIDATE:
 assert json.loads((current/'manifest.json').read_text())['commit']==CANDIDATE
 assert not list(pathlib.Path('/var/lib/graphato-host/postdeploy/runs').glob('*.json'))
else:assert not current.exists()
pool=[{'base':'10.211.0.0/16','size':24}]
network=ipaddress.ip_network(pool[0]['base'])
def command(*args,timeout=120):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=timeout).strip()
routes=json.loads(command('ip','-j','-4','route','show'))
path=pathlib.Path('/etc/docker/daemon.json');assert not path.is_symlink()
old=path.read_bytes() if path.exists() else b'{}'
config=json.loads(old);changed=config.get('default-address-pools')!=pool
overlaps=[row for row in routes if row.get('dst') not in (None,'default') and network.overlaps(ipaddress.ip_network(row['dst']))]
if changed:assert not overlaps,'Reserved pool overlaps an existing guest route'
elif overlaps:
 ids=command('docker','network','ls','-q').splitlines()
 existing=json.loads(command('docker','network','inspect',*ids))
 docker_subnets={item['Subnet'] for entry in existing for item in (entry['IPAM'].get('Config') or []) if 'Subnet' in item}
 assert all(row['dst'] in docker_subnets and (row.get('dev','').startswith('br-') or row.get('dev')=='docker0') for row in overlaps)
record={'application_commit':CANDIDATE,'pool':pool,'config_changed':changed,'previous_config_sha256':hashlib.sha256(old).hexdigest()}
if changed:
 assert 'default-address-pools' not in config,'Inspect an existing custom pool before changing it'
 folder=pathlib.Path('/var/lib/leroy-vm/network-fix');folder.mkdir(mode=0o700,exist_ok=True)
 backup=folder/'daemon-before.json'
 if backup.exists():assert backup.read_bytes()==old
 else:backup.write_bytes(old);backup.chmod(0o600)
 config['default-address-pools']=pool
 staged=folder/'daemon-candidate.json';staged.write_text(json.dumps(config,indent=2)+'\n');staged.chmod(0o600)
 command('dockerd','--validate','--config-file',str(staged),timeout=30)
 lifecycle=folder/'lifecycle.py';lifecycle.write_text(LIFECYCLE)
 acme=pathlib.Path('/etc/systemd/system/leroy-test-acme.service').exists()
 if current.exists():command('python3',str(lifecycle),'stop',timeout=180)
 if acme:command('systemctl','stop','leroy-test-acme.service',timeout=60)
 try:
  path.write_bytes(staged.read_bytes());path.chmod(0o600)
  command('systemctl','restart','docker.service',timeout=120)
 except Exception:
  path.write_bytes(old);command('systemctl','restart','docker.service',timeout=120)
  raise
 finally:
  if acme:command('systemctl','start','leroy-test-acme.service',timeout=120)
  if current.exists():command('python3',str(lifecycle),'start',timeout=240)
effective=json.loads(command('docker','info','--format','{{json .DefaultAddressPools}}'))
assert [{'base':row.get('Base',row.get('base')),'size':row.get('Size',row.get('size'))} for row in effective]==pool
created=[];record['networks']=[]
record['route_before']=command('ip','-4','route','get','172.23.0.1')
try:
 for index in range(4):
  name='leroy-network-fixed-proof-'+str(index)
  assert name not in command('docker','network','ls','--format','{{.Name}}').splitlines()
  identity=command('docker','network','create','--label','io.leroy.nas-parity=network-proof',name)
  created.append((identity,name))
  info=json.loads(command('docker','network','inspect',identity))[0]
  assert all(ipaddress.ip_network(row['Subnet']).subnet_of(network) for row in info['IPAM']['Config'])
  assert command('ip','-4','route','get','172.23.0.1')==record['route_before']
  record['networks'].append({'name':name,'subnets':info['IPAM']['Config']})
 for tick in range(HOLD_SECONDS//10):
  time.sleep(10)
  assert command('ip','-4','route','get','172.23.0.1')==record['route_before']
  print('SSH proof tick '+str(tick+1),flush=True)
finally:
 for identity,name in reversed(created):
  info=json.loads(command('docker','network','inspect',identity))[0]
  assert info['Name']==name and info['Labels'].get('io.leroy.nas-parity')=='network-proof'
  command('docker','network','rm',identity)
record['route_after']=command('ip','-4','route','get','172.23.0.1')
assert record['route_after']==record['route_before']
record.update(held_seconds=HOLD_SECONDS,passed=True)
print(json.dumps(record))
"""


def configure(candidate=None, hold_seconds=0):
    assert candidate is None or re.fullmatch("[a-f0-9]{40}", candidate)
    assert hold_seconds in (0, 70)
    values = {
        "CANDIDATE": candidate, "HOLD_SECONDS": hold_seconds,
        "LIFECYCLE": (ROOT / "infra/vm/graphato-lifecycle.py").read_text(),
    }
    program = "\n".join(key + "=" + repr(value) for key, value in values.items()) + "\n" + PROGRAM
    compile(program, "isolated-vm-network-policy", "exec")
    result = guest("sudo python3 -", program, timeout=600)
    rows = result.splitlines()
    record = {"at": datetime.now(timezone.utc).isoformat(), **json.loads(rows[-1])}
    label = candidate[:12] if candidate else "fresh"
    folder = ROOT / "test-results/nas-parity/followup/vm-network"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (label + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    path.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate")
    parser.add_argument("--hold-seconds", type=int, choices=[0, 70], default=0)
    arguments = parser.parse_args()
    configure(arguments.candidate, arguments.hold_seconds)
