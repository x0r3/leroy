"""Install ordered start/stop only for Graphato in the explicitly isolated VM."""

from test_support import ROOT
from test_vm import guest

unit = """[Unit]
Description=Ordered Graphato lifecycle in the isolated Leroy acceptance VM
After=docker.service apparmor.service leroy-test-acme.service
Requires=docker.service leroy-test-acme.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/python3 /usr/local/libexec/leroy-test-graphato.py start
ExecStop=/usr/bin/python3 /usr/local/libexec/leroy-test-graphato.py stop
TimeoutStartSec=240
TimeoutStopSec=180
[Install]
WantedBy=multi-user.target
"""
files = {
    "/usr/local/libexec/leroy-test-graphato.py": (ROOT / "infra/vm/graphato-lifecycle.py").read_text(
        encoding="utf-8"
    ),
    "/etc/systemd/system/leroy-test-graphato.service": unit,
}
program = f"""from pathlib import Path
import subprocess
assert Path('/var/lib/leroy-vm/ready').is_file()
for name, contents in {files!r}.items():
    Path(name).write_text(contents)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemctl', 'enable', '--now', 'leroy-test-graphato.service'], check=True)
print('Ordered Graphato VM lifecycle enabled')
"""
print(guest("sudo python3 -", data=program))
