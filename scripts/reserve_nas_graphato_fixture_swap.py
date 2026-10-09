"""Reserve swap for test Jenkins/Gitea without changing original builder limits."""

import json
from datetime import datetime, timezone

from align_nas_graphato_budget import MEMORY, OWNED
from nas_ssh import ROOT, run_script
from stage_nas_production_graphato import COMMIT

PROGRAM = r'''
import hashlib,json,pathlib,subprocess,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
metadata=pathlib.Path('/volume1/@docker/containers',OWNED)
config=json.loads((metadata/'config.v2.json').read_text())
assert config['ID']==OWNED and config['Name']=='/leroy-nas-parity-docker-1'
group=pathlib.Path('/sys/fs/cgroup/system.slice','docker-'+OWNED+'.scope')
assert (group/'memory.max').read_text().strip()==str(MEMORY)
assert (group/'memory.swap.max').read_text().strip()==str(BUILDER_SWAP)
before=int((group/'memory.swap.current').read_text());assert before>=BUILDER_SWAP-16*1024**2
free=int(next(line.split()[1] for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith('SwapFree:')))*1024
assert free>=2*RESERVE,'Do not exhaust host swap for the fixture'
path=root/'compose.yaml';original=path.read_bytes();text=original.decode()
assert text.count('memswap_limit: 6656m')==1 and text.count('mem_limit: 4608m')==1
backup=root/'compose-before-fixture-swap-reserve.yaml';assert not backup.exists();backup.write_bytes(original);backup.chmod(0o600)
(group/'memory.swap.max').write_text(str(BUILDER_SWAP+RESERVE))
result=subprocess.run(['docker','update','--memory',str(MEMORY),'--memory-swap',str(MEMORY+BUILDER_SWAP+RESERVE),OWNED],capture_output=True,text=True,timeout=90)
assert result.returncode==0,result.stderr[-1000:]
desired=text.replace('memswap_limit: 6656m','memswap_limit: 7680m',1);path.write_text(desired)
host=json.loads((metadata/'hostconfig.json').read_text())
assert host['Memory']==MEMORY and host['MemorySwap']==MEMORY+BUILDER_SWAP+RESERVE
assert (group/'memory.max').read_text().strip()==str(MEMORY)
assert (group/'memory.swap.max').read_text().strip()==str(BUILDER_SWAP+RESERVE)
print(json.dumps({'at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'owned_daemon':OWNED,'memory_bytes':MEMORY,'memory_swap_bytes':MEMORY+BUILDER_SWAP+RESERVE,'parent_swap_limit_bytes':BUILDER_SWAP+RESERVE,'original_builder_swap_limit_bytes':BUILDER_SWAP,'fixture_swap_reserve_bytes':RESERVE,'host_swap_free_before_bytes':free,'before_swap_current':before,'runtime_and_docker_config_matched':True,'compose_persisted':True,'compose_before_sha256':hashlib.sha256(original).hexdigest(),'compose_after_sha256':hashlib.sha256(desired.encode()).hexdigest(),'original_builder_resource_limits_changed':False,'jenkins_run_started_under_previous_budget':True,'performance_comparison_valid':False,'daemon_restarted':False,'production_modified':False}))
'''


def main():
    folder = ROOT / "test-results/nas-parity/followup/candidates/graphato" / COMMIT
    path = folder / "fixture-swap-reserve.json"
    assert not path.exists(), "No implicit resource-policy repetition"
    previous = json.loads((folder / "original-builder-swap-alignment.json").read_text())
    assert previous["runtime_and_docker_config_matched"] and previous["parent_swap_limit_bytes"] == 2 * 1024**3
    (folder / "fixture-swap-reserve-started.json").write_text(json.dumps({
        "at": datetime.now(timezone.utc).isoformat(), "commit": COMMIT,
        "original_builder_swap_limit_bytes": 2 * 1024**3, "fixture_swap_reserve_bytes": 1024**3,
        "parent_swap_limit_bytes": 3 * 1024**3, "production_modified": False,
        "performance_comparison_valid": False,
    }, indent=2) + "\n")
    program = f"OWNED={OWNED!r}\nMEMORY={MEMORY!r}\nBUILDER_SWAP={2 * 1024**3!r}\nRESERVE={1024**3!r}\n" + PROGRAM
    result = run_script("python3 - <<'PY'\n" + program + "\nPY\n", ROOT / ".local/nas-ssh.json", sudo=True, timeout=120)
    if result.returncode:
        (folder / "fixture-swap-reserve-failure.json").write_text(json.dumps({
            "at": datetime.now(timezone.utc).isoformat(), "complete": False, "error": result.stderr[-1500:],
        }, indent=2) + "\n")
        raise RuntimeError(result.stderr[-1500:])
    record = {**json.loads(result.stdout), "application_patches_applied": False,
              "original_builder_evidence": previous["original_builder"], "same_policy_for_leroy_intended": True}
    path.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))


if __name__ == "__main__":
    main()
