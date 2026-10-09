"""Correct the owned parent budget; never reinterpret the affected run as a benchmark."""

import argparse
import json
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script
from stage_nas_production_graphato import COMMIT

OWNED = "7d029e17dc28b04ec41ac927360062f057c97564227c62e7e01a50a4938b5a00"
MEMORY = 4608 * 1024**2
PROGRAM = r'''
import hashlib,json,pathlib,subprocess,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert (root/'.leroy-owned').is_file()
metadata=pathlib.Path('/volume1/@docker/containers',OWNED)
config=json.loads((metadata/'config.v2.json').read_text())
assert config['ID']==OWNED and config['Name']=='/leroy-nas-parity-docker-1'
group=pathlib.Path('/sys/fs/cgroup/system.slice','docker-'+OWNED+'.scope')
def snapshot():
 return {name:(group/name).read_text().strip() for name in ('memory.current','memory.max','memory.swap.current','memory.swap.max','memory.events','memory.pressure','io.pressure')}
before=snapshot()
assert before['memory.max'] in ({str(3*1024**3),str(MEMORY)} if RESUME else {str(3*1024**3)})
assert before['memory.swap.max']=='0'
compose=root/'compose.yaml';raw=compose.read_bytes();text=raw.decode()
assert text.count('mem_limit: 3072m')==1 and text.count('memswap_limit: 3072m')==1
backup=root/'compose-before-graphato-parent-budget.yaml'
if RESUME:assert backup.read_bytes()==raw
else:
 assert not backup.exists();backup.write_bytes(raw);backup.chmod(0o600)
subprocess.run(['docker','update','--memory',str(MEMORY),'--memory-swap',str(MEMORY),OWNED],check=True,timeout=90,capture_output=True)
after=snapshot();assert after['memory.max']==str(MEMORY) and after['memory.swap.max']=='0'
text=text.replace('mem_limit: 3072m','mem_limit: 4608m',1).replace('memswap_limit: 3072m','memswap_limit: 4608m',1)
compose.write_text(text)
host=json.loads((metadata/'hostconfig.json').read_text())
assert host['Memory']==host['MemorySwap']==MEMORY
print(json.dumps({'at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'owned_daemon':OWNED,'before':before,'after':after,'compose_before_sha256':hashlib.sha256(raw).hexdigest(),'compose_after_sha256':hashlib.sha256(text.encode()).hexdigest(),'daemon_restarted':False,'additional_swap_allowed':False,'production_modified':False}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-only", action="store_true", help="Relieve the exact owned cgroup while Docker's update request is blocked")
    parser.add_argument("--persist-after-relief", action="store_true", help="Finish the recorded runtime correction after the first Docker update timed out")
    parser.add_argument("--persist-compose-only", action="store_true", help="Persist the verified fixture budget without making another blocked Docker API request")
    args = parser.parse_args()
    folder = ROOT / "test-results/nas-parity/followup/candidates/graphato" / COMMIT
    if args.persist_compose_only:
        assert (folder / "parent-budget-runtime-relief.json").exists()
        program = r'''
import hashlib,json,pathlib,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
metadata=pathlib.Path('/volume1/@docker/containers',OWNED)
config=json.loads((metadata/'config.v2.json').read_text())
assert config['ID']==OWNED and config['Name']=='/leroy-nas-parity-docker-1'
group=pathlib.Path('/sys/fs/cgroup/system.slice','docker-'+OWNED+'.scope')
assert (group/'memory.max').read_text().strip()==str(MEMORY) and (group/'memory.swap.max').read_text().strip()=='0'
original=(root/'compose-before-graphato-parent-budget.yaml').read_bytes()
assert original.decode().count('mem_limit: 3072m')==1 and original.decode().count('memswap_limit: 3072m')==1
desired=original.decode().replace('mem_limit: 3072m','mem_limit: 4608m',1).replace('memswap_limit: 3072m','memswap_limit: 4608m',1)
path=root/'compose.yaml';assert path.read_bytes() in {original,desired.encode()};path.write_text(desired)
host=json.loads((metadata/'hostconfig.json').read_text())
print(json.dumps({'at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'owned_daemon':OWNED,'compose_persisted':True,'runtime_memory_bytes':MEMORY,'docker_hostconfig_memory_bytes':host['Memory'],'docker_hostconfig_memory_swap_bytes':host['MemorySwap'],'runtime_and_docker_config_matched':host['Memory']==host['MemorySwap']==MEMORY,'compose_before_sha256':hashlib.sha256(original).hexdigest(),'compose_after_sha256':hashlib.sha256(desired.encode()).hexdigest(),'production_modified':False,'additional_swap_allowed':False,'daemon_restarted':False}))
'''
        result = run_script("python3 - <<'PY'\nOWNED=" + repr(OWNED) + "\nMEMORY=" + repr(MEMORY) + "\n" + program + "\nPY\n",
                            ROOT / ".local/nas-ssh.json", sudo=True, timeout=45)
        if result.returncode:
            raise RuntimeError(result.stderr[-1500:])
        record = json.loads(result.stdout)
        (folder / "parent-budget-compose-persistence.json").write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(record))
        return
    if args.runtime_only:
        started = json.loads((folder / "parent-budget-correction-started.json").read_text())
        assert started["commit"] == COMMIT and started["corrected_parent_memory_bytes"] == MEMORY
        destination = folder / "parent-budget-runtime-relief.json"
        assert not destination.exists(), "No implicit runtime correction repetition"
        program = r'''
import json,pathlib,time
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
metadata=pathlib.Path('/volume1/@docker/containers',OWNED)
config=json.loads((metadata/'config.v2.json').read_text())
assert config['ID']==OWNED and config['Name']=='/leroy-nas-parity-docker-1'
group=pathlib.Path('/sys/fs/cgroup/system.slice','docker-'+OWNED+'.scope')
before=(group/'memory.max').read_text().strip()
assert before in {str(3*1024**3),str(MEMORY)} and (group/'memory.swap.max').read_text().strip()=='0'
if before!=str(MEMORY):(group/'memory.max').write_text(str(MEMORY))
assert (group/'memory.max').read_text().strip()==str(MEMORY)
print(json.dumps({'at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'owned_daemon':OWNED,'memory_max_before':int(before),'memory_max_after':MEMORY,'docker_configuration_update_still_required':True,'production_modified':False,'additional_swap_allowed':False}))
'''
        result = run_script("python3 - <<'PY'\nOWNED=" + repr(OWNED) + "\nMEMORY=" + repr(MEMORY) + "\n" + program + "\nPY\n",
                            ROOT / ".local/nas-ssh.json", sudo=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stderr[-1500:])
        record = json.loads(result.stdout)
        destination.write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(record))
        return
    destination = folder / "parent-budget-correction.json"
    assert not destination.exists(), "Inspect the retained correction before repeating it"
    inventory = json.loads((ROOT / "test-results/nas-parity/nas-inventory.json").read_text())
    production = next(row for row in inventory["containers"] if row["name"] == "jenkins")
    assert production["memory"] == 0
    invocation = {"at": datetime.now(timezone.utc).isoformat(), "commit": COMMIT,
                  "jenkins_build_in_progress": 5, "previous_parent_memory_bytes": 3 * 1024**3,
                  "corrected_parent_memory_bytes": MEMORY, "production_jenkins_memory_limit": 0,
                  "jenkins_run_started_under_previous_budget": True, "performance_comparison_valid": False,
                  "application_source_or_test_deadlines_changed": False, "production_modified": False}
    if args.persist_after_relief:
        assert (folder / "parent-budget-runtime-relief.json").exists()
        invocation = json.loads((folder / "parent-budget-correction-started.json").read_text())
        invocation["configuration_update_resumed_at"] = datetime.now(timezone.utc).isoformat()
    else:
        (folder / "parent-budget-correction-started.json").write_text(json.dumps(invocation, indent=2) + "\n")
    values = "OWNED=" + repr(OWNED) + "\nMEMORY=" + repr(MEMORY) + "\nRESUME=" + repr(args.persist_after_relief) + "\n"
    result = run_script("python3 - <<'PY'\n" + values + PROGRAM + "\nPY\n", ROOT / ".local/nas-ssh.json", sudo=True, timeout=120)
    if result.returncode:
        (folder / ("parent-budget-update-failure-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")).write_text(json.dumps({
            "recorded_at": datetime.now(timezone.utc).isoformat(), "completed": False,
            "production_modified": False, "error": result.stderr[-1500:],
        }, indent=2) + "\n")
        raise RuntimeError(result.stderr[-1500:])
    record = {**invocation, **json.loads(result.stdout), "same_corrected_parent_budget_for_leroy": True}
    destination.write_text(json.dumps(record, indent=2) + "\n")
    local = ROOT / ".local/nas-parity/compose.yaml"
    if local.exists():
        raw = local.read_bytes()
        (local.parent / "compose-before-graphato-parent-budget.yaml").write_bytes(raw)
        local.write_text(raw.decode().replace("mem_limit: 3072m", "mem_limit: 4608m", 1).replace("memswap_limit: 3072m", "memswap_limit: 4608m", 1))
    print(json.dumps({"corrected_parent_memory_bytes": MEMORY, "additional_swap_allowed": False,
                      "daemon_restarted": False, "performance_comparison_valid": False}))


if __name__ == "__main__":
    main()
