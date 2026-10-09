"""Sequence the resource-intensive acceptance runs on this finite test host."""

import json
import subprocess
import sys
import time
from contextlib import closing

from test_support import ROOT, api, wait
from test_vm import close_guest, guest

if len(sys.argv) != 2:
    raise SystemExit("Pass the existing Graphato acceptance run to finish first")
with closing(api()) as client:
    result = wait(client, sys.argv[1], timeout=29000)
print("Original Graphato acceptance finished:", result["status"], flush=True)
before_boot = guest("cat /proc/sys/kernel/random/boot_id")
assert guest("curl -fsS -o /dev/null -w '%{http_code}' https://graphato.test/") == "200"
close_guest()
shutdown_started = time.time()
subprocess.run([sys.executable, "scripts/vm.py", "stop"], cwd=ROOT, check=True)
shutdown_path = ROOT / "test-results/vm/sequenced-shutdown.json"
subprocess.run(["docker", "cp", "leroy-linux-vm:/vm/shutdown.json", str(shutdown_path)], check=True)
shutdown = json.loads(shutdown_path.read_text(encoding="utf-8"))
assert shutdown["forced"] is False and shutdown["qemu_exit_code"] == 0
assert shutdown["finished_at"] >= shutdown_started, "Shutdown evidence is stale"
try:
    antares = subprocess.run([sys.executable, "scripts/test_antares_validation.py"], cwd=ROOT)
finally:
    subprocess.run([sys.executable, "scripts/vm.py", "start"], cwd=ROOT, check=True)
deadline = time.monotonic() + 180
while time.monotonic() < deadline:
    try:
        if (
            guest("systemctl is-active leroy-test-acme.service leroy-test-graphato.service")
            == "active\nactive"
            and guest("curl -fsS -o /dev/null -w '%{http_code}' https://graphato.test/") == "200"
        ):
            break
    except RuntimeError:
        pass
    time.sleep(3)
else:
    raise TimeoutError("VM test services and Graphato did not recover after restart")
after_boot = guest("cat /proc/sys/kernel/random/boot_id")
assert before_boot != after_boot
assert guest("cat /sys/module/apparmor/parameters/enabled") == "Y"
(ROOT / "test-results/vm/application-restart.json").write_text(
    json.dumps(
        {
            "before_boot": before_boot,
            "after_boot": after_boot,
            "https_before": 200,
            "https_after": 200,
            "apparmor_after": True,
            "ordered_shutdown": True,
            "shutdown": shutdown,
            "manual_ownership_recovery_after_restart": False,
            "status": "passed",
        },
        indent=2,
    ),
    encoding="utf-8",
)
print("Graphato, ACME and AppArmor recovered after ordered VM restart", flush=True)
graphato = subprocess.run([sys.executable, "scripts/test_graphato_validation.py"], cwd=ROOT)
raise SystemExit(antares.returncode or graphato.returncode)
