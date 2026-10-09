"""Validate saved Compose resource limits without recreating or restarting any service."""

import json
from datetime import datetime, timezone

from align_nas_graphato_budget import MEMORY, OWNED
from nas_ssh import ROOT, run_script
from stage_nas_production_graphato import COMMIT

PROGRAM = r'''
import json,pathlib,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
metadata=pathlib.Path('/volume1/@docker/containers',OWNED)
config=json.loads((metadata/'config.v2.json').read_text())
assert config['ID']==OWNED and config['Name']=='/leroy-nas-parity-docker-1'
rendered=subprocess.check_output(['docker','compose','-f',str(root/'compose.yaml'),'config','--format','json'],cwd=root,text=True,timeout=30)
service=json.loads(rendered)['services']['docker']
limits={key:service[key] for key in ('mem_limit','memswap_limit','cpus')}
host=json.loads((metadata/'hostconfig.json').read_text())
group=pathlib.Path('/sys/fs/cgroup/system.slice','docker-'+OWNED+'.scope')
assert int(limits['mem_limit'])==host['Memory']==int((group/'memory.max').read_text())==MEMORY
assert int(limits['memswap_limit'])==host['MemorySwap']==MEMORY+3*1024**3
assert int((group/'memory.swap.max').read_text())==3*1024**3
assert float(limits['cpus'])==6
print(json.dumps({'read_only':True,'compose_rendered_limits':limits,'runtime_and_saved_limits_match':True,'services_recreated':False,'production_modified':False,'original_builder_limits_changed':False}))
'''


def main():
    folder = ROOT / "test-results/nas-parity/followup/candidates/graphato" / COMMIT
    destination = folder / "compose-budget-validation.json"
    assert not destination.exists(), "No implicit repetition"
    result = run_script("python3 - <<'PY'\nOWNED=" + repr(OWNED) + "\nMEMORY=" + repr(MEMORY) + "\n" + PROGRAM + "\nPY\n", ROOT / ".local/nas-ssh.json", sudo=True, timeout=45)
    if result.returncode:
        failure = {"at": datetime.now(timezone.utc).isoformat(), "read_only": True,
                   "complete": False, "services_recreated": False,
                   "compose_plugin_missing": "is not a docker command" in result.stderr or "unknown command" in result.stderr,
                   "assertion_failed": "AssertionError" in result.stderr,
                   "error_type": "NativeComposeValidationFailure"}
        if result.stdout.strip():
            failure["observed"] = json.loads(result.stdout)
        (folder / "compose-budget-validation-failure.json").write_text(json.dumps(failure, indent=2) + "\n")
        raise RuntimeError(json.dumps(failure))
    record = {**json.loads(result.stdout), "at": datetime.now(timezone.utc).isoformat(), "commit": COMMIT}
    destination.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))


if __name__ == "__main__":
    main()
