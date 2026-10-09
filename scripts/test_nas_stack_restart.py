"""Restart every owned NAS test service, preserving storage and isolation."""

import argparse
import json
import re
import time
from contextlib import closing

from compare_nas_antares import client
from nas_followup_support import remote
from nas_ssh import ROOT

PROGRAM = r"""
import json,pathlib,subprocess,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert (root/'.leroy-owned').is_file()
prefix='leroy-nas-parity-'
names={s:prefix+s+'-1' for s in ['controller','runner','postgres','docker','vm-access']}
def command(*args):return subprocess.check_output(list(args),timeout=180)
def inner(*args):return command('docker','exec',names['docker'],'docker',*args)
def states():
 rows=json.loads(command('docker','inspect',*names.values()))
 for row in rows:assert row['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
 return {r['Name'].lstrip('/'): {'id':r['Id'],'image':r['Image'],'started_at':r['State']['StartedAt'],
  'mounts':sorted([{k:m.get(k) for k in ['Type','Name','Source','Destination']} for m in r['Mounts']],key=lambda m:m['Destination'])} for r in rows}
def database():
 sql="SELECT json_build_object('runs',(SELECT count(*) FROM runs),'events',(SELECT count(*) FROM events),'artifacts',(SELECT count(*) FROM artifacts),'active',(SELECT count(*) FROM runs WHERE status IN ('running','queued','waiting')))"
 return json.loads(command('docker','exec',names['postgres'],'psql','-U','leroy','-d','leroy','-At','-c',sql))
before=states()
db_before=database()
assert db_before['active']==0
deadline=time.monotonic()+60
while time.monotonic()<deadline:
 running=set(inner('ps','--format','{{.Names}}').decode().split())
 if running=={'gitea','registry'}:break
 time.sleep(3)
else:raise RuntimeError('Expected only the idle owned registry and Gitea')
inner_before={}
for name in sorted(running):
 info=json.loads(inner('inspect',name))[0]
 assert info['Config']['Labels']['io.leroy.nas-parity']=='true'
 inner_before[name]={'id':info['Id'],'image':info['Image'],'mounts':info['Mounts']}
inner('stop',*sorted(running))
command('docker','stop',names['runner'],names['controller'],names['docker'],names['postgres'],names['vm-access'])
stopped=json.loads(command('docker','inspect',*names.values()))
assert all(not row['State']['Running'] for row in stopped)
command('docker','start',names['postgres'],names['docker'],names['vm-access'])
deadline=time.monotonic()+180
while time.monotonic()<deadline:
 rows=json.loads(command('docker','inspect',names['postgres'],names['docker']))
 if all(row['State'].get('Health',{}).get('Status')=='healthy' for row in rows):break
 time.sleep(3)
else:raise TimeoutError('Owned storage services did not recover')
inner('start',*sorted(running))
command('docker','start',names['controller'],names['runner'])
after=states()
for name in before:
 assert before[name]['id']==after[name]['id'] and before[name]['image']==after[name]['image']
 assert before[name]['mounts']==after[name]['mounts'] and before[name]['started_at']!=after[name]['started_at']
for name,old in inner_before.items():
 info=json.loads(inner('inspect',name))[0]
 assert info['State']['Running'] and info['Id']==old['id'] and info['Image']==old['image']
 assert sorted(info['Mounts'],key=lambda m:m['Destination'])==sorted(old['mounts'],key=lambda m:m['Destination'])
db_after=database()
assert db_before==db_after
rules=command('docker','exec',names['docker'],'iptables','-S','LEROY-PARITY-EGRESS').decode()
assert '-d 192.168.0.0/16 -j REJECT' in rules
assert '-d 10.232.98.10/32 -p tcp -m tcp --dport 8088 -j RETURN' in rules
assert '-d 10.232.98.11/32 -p tcp -m tcp --dport 12225 -j RETURN' in rules
for ref in REGISTRY_REFS:
 assert ref.startswith('registry:5000/home-lab/') and '@sha256:' in ref
 inner('pull',ref)
print(json.dumps({'before':before,'after':after,'database':db_after,'nested_services':list(inner_before),
 'full_stop_and_start':True,'same_containers_images_and_mounts':True,'isolation_rules_restored':True,'rules':rules,
 'registry_digests_retrieved_after_restart':REGISTRY_REFS}))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", help="Separate evidence for an explicit repaired-environment retry")
    args = parser.parse_args()
    base = ROOT / "test-results/nas-parity/followup/nas-stack-restart"
    folder = base
    if args.attempt:
        assert re.fullmatch(r"[a-z0-9-]+", args.attempt)
        folder = base / "attempts" / args.attempt
    folder.mkdir(parents=True, exist_ok=True)
    assert not (folder / "started.json").exists(), "Inspect previous restart evidence first"
    with closing(client()) as api:
        for status in ("queued", "running", "waiting"):
            assert not api.get("/api/runs", params={"status": status}).json()
        assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
    (folder / "started.json").write_text(json.dumps({"at": time.time()}) + "\n")
    images = json.loads((base.parent / "home-lab-build/leroy-images.json").read_text())
    refs = [item["digests"][0] for item in images.values()]
    report = json.loads(remote("REGISTRY_REFS=" + repr(refs) + "\n" + PROGRAM, timeout=600))
    for _ in range(60):
        try:
            with closing(client()) as api:
                response = api.get("/health/ready")
                response.raise_for_status()
                assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
            break
        except Exception:
            time.sleep(2)
    else:
        raise TimeoutError("NAS UI did not return")
    report.update(controller_ready=True, automatic_triggers_disabled=True, passed=True)
    (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if args.attempt:
        report["successful_attempt"] = args.attempt
        (base / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("before", "after", "rules")}), flush=True)


if __name__ == "__main__":
    main()
