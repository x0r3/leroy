"""Prepare only test infrastructure in the fresh NAS comparison VM."""

import argparse
import ast
import json
import subprocess
import time

from nas_ssh import ROOT

LOCAL = ROOT / ".local/nas-parity"


def guest(command, data=None, timeout=600):
    args = [
        "ssh",
        "-i",
        str(ROOT / ".local/vm/id_ed25519"),
        "-p",
        "2225",
        "-o",
        "UserKnownHostsFile=" + str(LOCAL / "vm/known_hosts"),
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=15",
        "leroy-admin@127.0.0.1",
        command,
    ]
    result = subprocess.run(
        args, input=data.encode() if data is not None else None, capture_output=True, timeout=timeout
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace")[-2000:])
    return result.stdout.decode(errors="replace")


def wait_guest_ready(timeout=240):
    """Wait for authenticated guest SSH and Docker, not just the QEMU container."""
    deadline = time.monotonic() + timeout
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            guest("test -f /var/lib/leroy-vm/ready && systemctl is-active --quiet docker.service",
                  timeout=min(15, remaining))
            return
        except RuntimeError as error:
            if any(message in str(error).lower() for message in (
                "permission denied", "host key verification failed", "remote host identification has changed",
            )):
                raise
        except subprocess.TimeoutExpired:
            pass
        time.sleep(min(3, max(0, deadline - time.monotonic())))
    raise TimeoutError("Test VM SSH/Docker did not become ready; no infrastructure changes applied")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", help="Use this separately frozen checkout for host package pins")
    args = parser.parse_args()
    baseline = json.loads((ROOT / "test-results/nas-parity/baseline.json").read_text())
    source = baseline["sources"]["graphato"]
    checkout = ROOT / source.get("local_checkout", ".sources/graphato")
    if args.candidate:
        from nas_candidate_paths import candidate_checkout

        checkout = candidate_checkout(args.candidate)
        source = {"commit": args.candidate}
    actual = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"]).decode().strip()
    assert actual == source["commit"], "Graphato preparation must use the frozen original revision"
    tree = ast.parse((checkout / "deployments/linux/host/bootstrap.py").read_text())
    pins = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "DOCKER_PACKAGES" for t in n.targets)
    )
    wait_guest_ready()
    # A restored snapshot can have overdue automatic upgrade timers. They
    # restarted system services during the original Jenkins bootstrap. Freeze
    # only background package updates on this owned fixture for both engines.
    package_updates = json.loads(guest("sudo python3 -", r'''
import json,pathlib,subprocess,time
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
units=['apt-daily.timer','apt-daily-upgrade.timer','update-notifier-download.timer','update-notifier-motd.timer']
subprocess.run(['systemctl','disable','--now',*units],check=True,capture_output=True)
pathlib.Path('/etc/apt/apt.conf.d/99leroy-acceptance').write_text('APT::Periodic::Enable "0";\n')
deadline=time.monotonic()+180
services=['apt-daily.service','apt-daily-upgrade.service']
while time.monotonic()<deadline:
 active=[u for u in services if subprocess.run(['systemctl','is-active','--quiet',u]).returncode==0]
 if not active:break
 time.sleep(2)
else:raise RuntimeError('Background upgrades still active; no bootstrap started')
assert all(subprocess.run(['systemctl','is-active','--quiet',u]).returncode!=0 for u in units)
print(json.dumps({'timers_disabled':units,'background_upgrades_inactive':True,'scope':'owned test VM only'}))
''', timeout=210))
    print("Automatic guest updates frozen:", json.dumps(package_updates), flush=True)
    guest("sudo -n test ! -e /opt/graphato/current", timeout=15)
    secrets = LOCAL / "config/test-secrets"
    for name in ("bootstrap", "deploy"):
        key = secrets / name
        if not key.exists():
            subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(key)],
                stdout=subprocess.DEVNULL,
                check=True,
            )
    public = (secrets / "bootstrap.pub").read_text().strip()
    assert public.startswith("ssh-ed25519 ") and "\n" not in public
    guest(
        "sudo install -d -m 700 /root/.ssh; sudo sh -c 'cat >> /root/.ssh/authorized_keys; sort -u /root/.ssh/authorized_keys -o /root/.ssh/authorized_keys; chmod 600 /root/.ssh/authorized_keys'",
        public + "\n",
    )
    program = f"""import json,pathlib,subprocess
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
assert not pathlib.Path('/opt/graphato/current').exists()
pins={pins!r}
installed={{p:subprocess.check_output(['dpkg-query','-W','-f=${{Version}}',p],text=True) for p in pins}}
if installed != pins:
 with open('/var/tmp/leroy-docker-pins.log','w') as log:
  subprocess.run(['env','DEBIAN_FRONTEND=noninteractive','apt-get','install','-y','--allow-downgrades',*[p+'='+v for p,v in pins.items()],'docker-ce-rootless-extras='+pins['docker-ce']],stdout=log,stderr=log,check=True)
print(json.dumps(pins))
"""
    print("Graphato host toolchain aligned:", guest("sudo python3 -", program).strip(), flush=True)
    from configure_nas_vm_networks import configure

    configure()
    subprocess.run(
        [
            "docker",
            "exec",
            "leroy-nas-target-vm",
            "sh",
            "-c",
            "iptables -C OUTPUT -d 11.254.254.254/32 -j REJECT 2>/dev/null || iptables -I OUTPUT 1 -d 11.254.254.254/32 -j REJECT",
        ],
        check=True,
    )
    unit = """[Unit]
Description=Isolated NAS parity DNS and ACME
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
    files = {
        "/var/lib/leroy-vm/acme/acme-directory.py": (ROOT / "infra/vm/acme-directory.py").read_text(),
        "/usr/local/libexec/leroy-test-acme": (ROOT / "infra/vm/setup-acme.sh").read_text(),
        "/etc/systemd/system/leroy-test-acme.service": unit,
    }
    program = f"""import pathlib,subprocess
for name,content in {files!r}.items():
 p=pathlib.Path(name);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','--now','leroy-test-acme.service'],check=True)
"""
    guest("sudo python3 -", program)
    evidence = {
        "kernel": guest("uname -r").strip(),
        "apparmor": guest("cat /sys/module/apparmor/parameters/enabled").strip(),
        "automatic_package_updates": package_updates,
        "docker_packages": pins,
        "application_installed": False,
        "acme": guest("systemctl is-active leroy-test-acme").strip(),
    }
    (ROOT / "test-results/nas-parity/vm-ready.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print("Fresh VM infrastructure ready; application bootstrap remains a pipeline task.")


if __name__ == "__main__":
    main()
