"""Permit only the original Graphato builder's measured two-GiB swap allowance."""

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
before_swap=(group/'memory.swap.max').read_text().strip();assert before_swap=='0'
before_current=(group/'memory.swap.current').read_text().strip()
path=root/'compose.yaml';original=path.read_bytes();text=original.decode()
assert text.count('memswap_limit: 4608m')==1 and text.count('mem_limit: 4608m')==1
backup=root/'compose-before-original-graphato-swap.yaml';assert not backup.exists();backup.write_bytes(original);backup.chmod(0o600)
# Relieve the exact owned cgroup first, so a slow Docker API cannot leave the
# original application's swap allowance blocked while waiting on storage.
(group/'memory.swap.max').write_text(str(SWAP))
assert (group/'memory.swap.max').read_text().strip()==str(SWAP)
result=subprocess.run(['docker','update','--memory',str(MEMORY),'--memory-swap',str(MEMORY+SWAP),OWNED],capture_output=True,text=True,timeout=90)
assert result.returncode==0,result.stderr[-1000:]
desired=text.replace('memswap_limit: 4608m','memswap_limit: 6656m',1);path.write_text(desired)
host=json.loads((metadata/'hostconfig.json').read_text())
assert host['Memory']==MEMORY and host['MemorySwap']==MEMORY+SWAP
print(json.dumps({'at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'owned_daemon':OWNED,'memory_bytes':MEMORY,'memory_swap_bytes':MEMORY+SWAP,'parent_swap_limit_bytes':SWAP,'before_swap_limit':int(before_swap),'before_swap_current':int(before_current),'after_swap_current':int((group/'memory.swap.current').read_text()),'runtime_and_docker_config_matched':True,'compose_persisted':True,'compose_before_sha256':hashlib.sha256(original).hexdigest(),'compose_after_sha256':hashlib.sha256(desired.encode()).hexdigest(),'original_builder_resource_limits_changed':False,'jenkins_run_started_under_previous_budget':True,'performance_comparison_valid':False,'daemon_restarted':False,'production_modified':False}))
'''


def main():
    folder = ROOT / "test-results/nas-parity/followup/candidates/graphato" / COMMIT
    path = folder / "original-builder-swap-alignment.json"
    assert not path.exists(), "No implicit resource-policy repetition"
    measured = ROOT / "test-results/nas-parity/followup/production-source-review/production-builder-budget.json"
    original = json.loads(measured.read_text(encoding="utf-8-sig"))
    assert original["read_only"] and not original["production_modified"]
    assert original["memory_bytes"] == 4 * 1024**3 and original["memory_swap_bytes"] == 6 * 1024**3
    swap = original["memory_swap_bytes"] - original["memory_bytes"]
    assert swap == 2 * 1024**3
    (folder / "original-builder-swap-alignment-started.json").write_text(json.dumps({
        "at": datetime.now(timezone.utc).isoformat(), "commit": COMMIT, "owned_daemon": OWNED,
        "measured_production_budget_evidence": measured.relative_to(ROOT).as_posix(),
        "parent_swap_limit_bytes": swap, "production_modified": False, "performance_comparison_valid": False,
    }, indent=2) + "\n")
    program = "OWNED=" + repr(OWNED) + "\nMEMORY=" + repr(MEMORY) + "\nSWAP=" + repr(swap) + "\n" + PROGRAM
    result = run_script("python3 - <<'PY'\n" + program + "\nPY\n", ROOT / ".local/nas-ssh.json", sudo=True, timeout=120)
    if result.returncode:
        (folder / "original-builder-swap-alignment-failure.json").write_text(json.dumps({
            "recorded_at": datetime.now(timezone.utc).isoformat(), "complete": False,
            "error": result.stderr[-1500:], "production_modified": False,
        }, indent=2) + "\n")
        raise RuntimeError(result.stderr[-1500:])
    record = {**json.loads(result.stdout), "original_builder": original,
              "application_patches_applied": False, "same_policy_for_leroy_intended": True}
    path.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))


if __name__ == "__main__":
    main()
