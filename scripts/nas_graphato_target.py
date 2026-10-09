"""Capture non-secret Graphato bootstrap evidence from the isolated VM."""

import argparse
import hashlib
import json
import subprocess

from nas_ssh import ROOT
from prepare_nas_vm import guest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", choices=["jenkins", "leroy"])
    args = parser.parse_args()
    results = ROOT / "test-results/nas-parity"
    source = json.loads((results / "baseline.json").read_text())["sources"]["graphato"]
    program = """import hashlib,json,pathlib,subprocess
def output(*args):return subprocess.check_output(args,text=True).strip()
root=pathlib.Path('/var/lib/graphato-host')
state=json.loads((root/'bootstrap.json').read_text())
packages={name:output('dpkg-query','-W','-f=${Version}',name) for name in state['dockerPackages']}
assert packages==state['dockerPackages']
hashes={}
for name in ['/usr/local/sbin/graphato-ci-receive','/usr/local/sbin/graphato-docker-firewall','/etc/apparmor.d/graphato-server','/etc/apparmor.d/graphato-test-rootlesskit','/etc/caddy/Caddyfile']:
 hashes[name]=hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()
services={name:output('systemctl','is-active',name) for name in ['docker','apparmor','fail2ban','caddy']}
endpoint=json.loads(pathlib.Path('/etc/graphato/public-endpoint.json').read_text())
assert endpoint['domain']=='graphato.test'
assert 'Status: active' in output('ufw','status')
assert 'graphato-server (enforce)' in pathlib.Path('/sys/kernel/security/apparmor/profiles').read_text()
print(json.dumps({'kernel':output('uname','-r'),'virtualization':output('systemd-detect-virt'),'packages':packages,'services':services,'source_hashes':hashes,'endpoint':endpoint,'firewall_active':True,'apparmor_enforced':True}))
"""
    state = json.loads(guest("sudo python3 -", program))
    mapping = {
        "/usr/local/sbin/graphato-ci-receive": "ci-receive.py",
        "/usr/local/sbin/graphato-docker-firewall": "docker-firewall.py",
        "/etc/apparmor.d/graphato-server": "graphato-server.apparmor",
        "/etc/apparmor.d/graphato-test-rootlesskit": "graphato-test-rootlesskit.apparmor",
    }
    for destination, name in mapping.items():
        contents = subprocess.check_output(
            [
                "git",
                "-C",
                str(ROOT / source["local_checkout"]),
                "show",
                source["commit"] + ":deployments/linux/host/" + name,
            ]
        )
        assert hashlib.sha256(contents).hexdigest() == state["source_hashes"][destination]
    state.update(source_commit=source["commit"], installed_source_matches_original=True)
    folder = results / "aligned/graphato-bootstrap-host"
    (folder / (args.engine + "-target-state.json")).write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps(state, indent=2))
    if args.engine == "leroy":
        assert state == json.loads((folder / "jenkins-target-state.json").read_text())
        print("Original bootstrap policy and observed host configuration match.")


if __name__ == "__main__":
    main()
