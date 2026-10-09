"""Reserve service addresses in the idle owned daemon after the failed restart."""

import argparse
import json

from nas_followup_support import remote
from nas_ssh import ROOT, upload_file

FOLDER = ROOT / "test-results/nas-parity/followup/nas-network-recovery"
SETUP = r"""
import json,pathlib,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert (root/'.leroy-owned').is_file()
prefix=['docker','exec','leroy-nas-parity-docker-1','docker']
def inner(*args):return subprocess.check_output([*prefix,*args],text=True,timeout=120)
"""
MIGRATE = r"""for service in ['controller','runner']:
 assert subprocess.check_output(['docker','inspect','leroy-nas-parity-'+service+'-1','--format','{{.State.Running}}'],text=True).strip()=='false'
assert set(inner('ps','--format','{{.Names}}').split())=={'gitea'}
network=json.loads(inner('network','inspect','leroy-jobs'))[0]
assert network['IPAM']['Config']==[{'Subnet':'10.234.98.0/24','Gateway':'10.234.98.1'}]
inner('stop','gitea')
assert not inner('ps','-q').strip()
rows=json.loads(inner('inspect',*inner('ps','-aq').split()))
attached={r['Name'].lstrip('/'):r['NetworkSettings']['Networks']['leroy-jobs'] for r in rows if 'leroy-jobs' in r['NetworkSettings']['Networks']}
before={r['Name'].lstrip('/'):{'id':r['Id'],'image':r['Image'],'mounts':r['Mounts']} for r in rows}
saved=root/'network-before-reservation.json'
assert not saved.exists()
saved.write_text(json.dumps({'network':network,'attachments':attached,'containers':before}))
for name in attached:inner('network','disconnect','leroy-jobs',name)
inner('network','rm','leroy-jobs')
inner('network','create','--subnet','10.234.98.0/24','--ip-range','10.234.98.128/25','--gateway','10.234.98.1','--label','io.leroy.nas-parity=true','leroy-jobs')
for name,endpoint in attached.items():
 args=['network','connect']
 fixed={'registry':'10.234.98.2','gitea':'10.234.98.3'}.get(name)
 if fixed:args+=['--ip',fixed]
 elif endpoint.get('IPAMConfig'):
  raise ValueError('Unexpected other static endpoint '+name)
 for alias in endpoint.get('Aliases') or []:args+=['--alias',alias]
 inner(*args,'leroy-jobs',name)
inner('start','gitea','registry')
"""
RESUME = r"""
saved=json.loads((root/'network-before-reservation.json').read_text())
before=saved['containers'];network=saved['network'];attached=saved['attachments']
actual=json.loads(inner('network','inspect','leroy-jobs'))[0]
assert actual['IPAM']['Config'][0]['IPRange']=='10.234.98.128/25'
for name,ip in [('registry','10.234.98.2'),('gitea','10.234.98.3')]:
 row=json.loads(inner('inspect',name))[0]
 assert row['State']['Running'] and row['NetworkSettings']['Networks']['leroy-jobs']['IPAddress']==ip
"""
FINISH = r"""for row in json.loads(inner('inspect',*inner('ps','-aq').split())):
 old=before[row['Name'].lstrip('/')]
 assert old['id']==row['Id'] and old['image']==row['Image']
 assert sorted(old['mounts'],key=lambda m:m['Destination'])==sorted(row['Mounts'],key=lambda m:m['Destination'])
subprocess.run(['docker','exec','leroy-nas-parity-docker-1','sh','-c',"grep -q '^10.234.98.2.*registry' /etc/hosts || printf '\\n10.234.98.2 registry\\n' >> /etc/hosts"],check=True)
subprocess.run(['docker','start','leroy-nas-parity-controller-1','leroy-nas-parity-runner-1'],check=True,stdout=subprocess.DEVNULL)
print(json.dumps({'same_container_images_ids_and_mounts':True,'network_before':network['Id'],'dynamic_range':'10.234.98.128/25','registry':'10.234.98.2','gitea':'10.234.98.3','reconnected':sorted(attached),'production_networks_changed':False}))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--finish",
        action="store_true",
        help="Verify and finish the recorded network migration without repeating it",
    )
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    assert not (FOLDER / "report.json").exists()
    upload_file(
        ROOT / "infra/nas/dind.sh", "/volume1/docker/leroy-nas-parity/dind.sh", ROOT / ".local/nas-ssh.json"
    )
    remote("import pathlib\npathlib.Path('/volume1/docker/leroy-nas-parity/dind.sh').chmod(0o644)")
    report = json.loads(remote(SETUP + (RESUME if args.finish else MIGRATE) + FINISH, timeout=360))
    (FOLDER / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
