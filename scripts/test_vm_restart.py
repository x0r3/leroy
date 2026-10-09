"""Verify graceful VM shutdown, an offline checkpoint and persistence after boot."""

import json
import subprocess
import sys
import time
import uuid

from test_vm import close_guest, guest
from vm import ROOT

marker = uuid.uuid4().hex
before = guest("cat /proc/sys/kernel/random/boot_id")
application_installed = (
    guest("if sudo test -e /opt/graphato/current; then printf yes; else printf no; fi") == "yes"
)
if "--require-application" in sys.argv:
    assert application_installed, "Graphato must be installed for the final acceptance restart"
if application_installed:
    assert (
        guest("systemctl is-active leroy-test-acme.service leroy-test-graphato.service") == "active\nactive"
    )
    assert guest("curl -fsS -o /dev/null -w '%{http_code}' https://graphato.test/") == "200"
guest("sudo tee /var/lib/leroy-vm/restart-proof >/dev/null", data=marker)
close_guest()
shutdown_started = time.time()
for action in (["stop"], ["snapshot", "baseline-" + marker[:8]], ["start"]):
    subprocess.run([sys.executable, str(ROOT / "scripts/vm.py"), *action], cwd=ROOT, check=True)

shutdown = json.loads(
    subprocess.check_output(
        [
            "docker",
            "exec",
            "leroy-linux-vm",
            "cat",
            "/vm/shutdown.json",
        ],
        text=True,
    )
)
assert shutdown["forced"] is False and shutdown["qemu_exit_code"] == 0
assert shutdown["finished_at"] >= shutdown_started, "Shutdown evidence is stale"
deadline = time.monotonic() + 120
while time.monotonic() < deadline:
    try:
        after = guest("cat /proc/sys/kernel/random/boot_id")
        if after != before:
            break
    except RuntimeError:
        pass
    time.sleep(2)
else:
    raise TimeoutError("VM did not return after restart")
assert guest("cat /var/lib/leroy-vm/restart-proof") == marker
assert guest("cat /sys/module/apparmor/parameters/enabled") == "Y"
guest("sudo docker info >/dev/null")
if application_installed:
    deadline = time.monotonic() + 240
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
        raise TimeoutError("The application did not recover after clean VM shutdown")
report = {
    "graceful_restart": "passed",
    "disk_persistence": "passed",
    "apparmor_after_restart": True,
    "offline_disk_snapshot": "baseline-" + marker[:8],
    "shutdown": shutdown,
    "application_https_before_and_after": 200 if application_installed else None,
    "manual_runtime_recovery_during_restart": False,
}
(ROOT / "test-results/vm/restart.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
