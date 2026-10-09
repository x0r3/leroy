"""Bootstrap the independently provisioned acceptance VM with original jobs."""

import json
import subprocess
import sys
import time
from contextlib import closing

from test_support import ROOT, api, evidence, start, wait
from test_vm import close_guest, guest

record = json.loads((ROOT / "test-results/vm/fresh-provision.json").read_text(encoding="utf-8"))
inspection = json.loads(subprocess.check_output(["docker", "inspect", "leroy-linux-vm"]))[0]
disk = next(mount["Name"] for mount in inspection["Mounts"] if mount["Destination"] == "/vm")
assert disk == record["fresh_disk"] and disk != record["previous_disk_preserved"]
print("Waiting for the new VM's cloud-init provisioning", flush=True)
deadline = time.monotonic() + 900
while time.monotonic() < deadline:
    try:
        guest("sudo test -f /var/lib/leroy-vm/ready")
        break
    except RuntimeError:
        time.sleep(5)
else:
    raise TimeoutError("Fresh VM provisioning did not finish")
assert guest("systemd-detect-virt") == "kvm"
guest("sudo test ! -e /opt/graphato/current")
close_guest()
for script in ["setup_graphato_vm.py", "setup_vm_acme.py", "setup_vm_lifecycle.py"]:
    print("Preparing", script, flush=True)
    subprocess.run([sys.executable, "scripts/" + script], cwd=ROOT, check=True)
results = []
with closing(api()) as client:
    for apply in [False, True]:
        run_id = start(
            client,
            "graphato-bootstrap-host",
            {"DOMAIN": "graphato.test", "TARGET_HOST": "graphato-vm", "APPLY_CHANGES": apply},
        )
        print("Fresh host bootstrap", "apply" if apply else "inspect", run_id, flush=True)
        run = wait(client, run_id, timeout=3600)
        evidence(client, run_id)
        results.append({"run": run_id, "apply": apply, "status": run["status"]})
        (ROOT / "test-results/vm/fresh-bootstrap.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )
        assert run["status"] == "succeeded"
subprocess.run([sys.executable, "scripts/test_vm.py"], cwd=ROOT, check=True)
print("Fresh VM original bootstrap and isolation checks passed", flush=True)
