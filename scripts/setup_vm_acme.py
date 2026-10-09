"""Emulate public DNS/ACME inside the VM without modifying upstream host policies."""

import subprocess
import sys

from vm import ROOT, ssh_args

sys.stdout.reconfigure(encoding="utf-8")

subprocess.run(
    [
        "docker",
        "exec",
        "leroy-linux-vm",
        "sh",
        "-c",
        "iptables -C OUTPUT -d 11.254.254.254/32 -j REJECT 2>/dev/null || iptables -I OUTPUT 1 -d 11.254.254.254/32 -j REJECT",
    ],
    check=True,
)
unit = """[Unit]
Description=Isolated Leroy DNS and ACME test infrastructure
After=docker.service network-online.target
Requires=docker.service
Before=caddy.service
[Service]
Type=oneshot
ExecStart=/bin/bash /usr/local/libexec/leroy-test-acme
ExecStop=/usr/bin/docker stop --time 15 leroy-acme-directory leroy-acme-pebble
TimeoutStopSec=40
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
"""
# One administrative session respects the unchanged upstream SSH rate limit.
files = {
    "/var/lib/leroy-vm/acme/acme-directory.py": (ROOT / "infra/vm/acme-directory.py").read_text(
        encoding="utf-8"
    ),
    "/usr/local/libexec/leroy-test-acme": (ROOT / "infra/vm/setup-acme.sh").read_text(encoding="utf-8"),
    "/etc/systemd/system/leroy-test-acme.service": unit,
}
program = f"""from pathlib import Path
import subprocess
assert Path('/var/lib/leroy-vm/ready').is_file()
for name, content in {files!r}.items():
    path = Path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
subprocess.run(['bash', '/usr/local/libexec/leroy-test-acme'], check=True)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemctl', 'enable', 'leroy-test-acme.service'], check=True)
"""
result = subprocess.run(
    [*ssh_args(), "sudo python3 -"], input=program.encode(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT
)
log = ROOT / "test-results/vm/acme-setup.log"
log.write_bytes(result.stdout)
print(result.stdout.decode(errors="replace")[-2500:])
raise SystemExit(result.returncode)
