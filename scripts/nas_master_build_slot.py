"""Wait for the NAS compiler slot, allowing observed remote postdeployment checks."""

import json
import time
from datetime import datetime, timezone

from nas_followup_support import production_jobs
from nas_ssh import ROOT, run_script
from stage_nas_production_graphato import COMMIT

PROGRAM = r'''
import json,pathlib
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
compilers=[]
for path in pathlib.Path('/proc').glob('[0-9]*'):
 try:
  name=(path/'comm').read_text().strip()
  if name in {'rustc','cargo','cc','ld','ld.lld'}:compilers.append(name)
 except (FileNotFoundError,PermissionError,ProcessLookupError):pass
available=int(next(line.split()[1] for line in pathlib.Path('/proc/meminfo').read_text().splitlines()
                   if line.startswith('MemAvailable:')))
print(json.dumps({'native_compilers':compilers,'available_memory_kib':available,'read_only':True}))
'''


def wait_for_nas_build_slot(commit=COMMIT):
    assert len(commit) == 40 and all(char in '0123456789abcdef' for char in commit)
    base = ROOT / "test-results/nas-parity/followup/candidates/graphato" / commit
    assert json.loads((base / "staged.json").read_text())["source_kind"] == "frozen_master_revision"
    deadline = time.monotonic() + 4 * 3600
    previous = None
    allowed = {"graphato-postdeploy-web", "graphato-postdeploy-quality", "graphato-release-acceptance"}
    while time.monotonic() < deadline:
        production = production_jobs()
        active = {name: row for name, row in production["jobs"].items() if row["building"]}
        result = run_script("python3 - <<'PY'\n" + PROGRAM + "\nPY\n", ROOT / ".local/nas-ssh.json",
                            sudo=True, timeout=45)
        assert result.returncode == 0, result.stderr[-1000:]
        state = json.loads(result.stdout)
        ready = set(active) <= allowed and not state["native_compilers"] and state["available_memory_kib"] >= 1024**2
        if (active, ready) != previous:
            print("NAS compiler slot:", json.dumps({"active_production_jobs": active, "ready": ready}), flush=True)
            previous = (active, ready)
        if ready:
            record = {"at": datetime.now(timezone.utc).isoformat(), "commit": commit,
                      "active_production_jobs": active, **state, "nas_compiler_slot_available": True,
                      "production_modified": False, "performance_comparison": False,
                      "scope": "Admission observation only; remote SSH quality/release jobs can remain active; background load is not asserted equal"}
            with (base / "nas-build-slot-observations.jsonl").open("a") as output:
                output.write(json.dumps(record) + "\n")
            return record
        time.sleep(45)
    raise TimeoutError("NAS build slot still unavailable; no production job was interrupted")
