"""Capture verified NAS resource conditions immediately before the unchanged-source counter-run."""

import json
from datetime import datetime, timezone

from align_nas_graphato_budget import MEMORY, OWNED
from nas_ssh import ROOT, run_script
from watch_nas_graphato_via_leroy import JENKINS_ID

PROGRAM = r'''
import json,pathlib,tomllib
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
metadata=pathlib.Path('/volume1/@docker/containers',OWNED)
config=json.loads((metadata/'config.v2.json').read_text())
assert config['ID']==OWNED and config['Name']=='/leroy-nas-parity-docker-1'
host=json.loads((metadata/'hostconfig.json').read_text())
group=pathlib.Path('/sys/fs/cgroup/system.slice','docker-'+OWNED+'.scope')
assert host['Memory']==int((group/'memory.max').read_text())==MEMORY
assert host['MemorySwap']==MEMORY+3*1024**3
assert int((group/'memory.swap.max').read_text())==3*1024**3
jenkins_path=pathlib.Path('/volume1/@docker/volumes/leroy-nas-parity_engine/_data/containers',JENKINS_ID,'config.v2.json')
jenkins=json.loads(jenkins_path.read_text())
assert jenkins['ID']==JENKINS_ID and jenkins['Name']=='/jenkins-parity'
assert not jenkins['State']['Running']
profile=tomllib.loads((root/'config/runner.toml').read_text())['profiles']['graphato']
assert profile['memory']==profile['memory_swap']=='2g'
print(json.dumps({'read_only':True,'owned_daemon':OWNED,'memory_bytes':MEMORY,'parent_swap_limit_bytes':3*1024**3,'original_builder_swap_limit_bytes':2*1024**3,'fixture_swap_reserve_bytes':1024**3,'job_control_memory_bytes':2*1024**3,'job_control_swap_limit_bytes':0,'runtime_and_saved_limits_match':True,'comparison_jenkins_stopped':True,'production_modified':False}))
'''


def record_start_budget(destination):
    assert not destination.exists(), "Retain the first counter-run start observation"
    program = f"OWNED={OWNED!r}\nMEMORY={MEMORY!r}\nJENKINS_ID={JENKINS_ID!r}\n" + PROGRAM
    result = run_script("python3 - <<'PY'\n" + program + "\nPY\n", ROOT / ".local/nas-ssh.json", sudo=True, timeout=45)
    assert result.returncode == 0, "Counter-run resource check failed; no pipeline started"
    record = {**json.loads(result.stdout), "at": datetime.now(timezone.utc).isoformat(),
              "identical_jenkins_starting_conditions_asserted": False, "performance_comparison_valid": False}
    destination.write_text(json.dumps(record, indent=2) + "\n")
    return destination.relative_to(ROOT).as_posix()
