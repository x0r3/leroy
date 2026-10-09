"""Validate the VM's own kernel, enforced AppArmor, Docker and isolation."""

import atexit
import base64
import json
import shlex
import subprocess
from datetime import datetime, timezone

from vm import ROOT, ssh_args

_connection = None
_EXECUTOR = """import base64,json,subprocess,sys
for line in sys.stdin:
    request=json.loads(line)
    try:
        result=subprocess.run(request['command'],shell=True,input=request['data'].encode() if request['data'] is not None else None,capture_output=True,timeout=180)
        response={'returncode':result.returncode,'stdout':base64.b64encode(result.stdout).decode(),'stderr':base64.b64encode(result.stderr).decode()}
    except Exception as error:
        response={'error':type(error).__name__}
    print(json.dumps(response),flush=True)
"""


def close_guest():
    global _connection
    if _connection is not None:
        _connection.stdin.close()
        try:
            _connection.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _connection.terminate()
        _connection = None


atexit.register(close_guest)


def guest(command, *, data=None):
    # Reuse one administrative connection: the real host policy rate-limits new
    # SSH connections. Binary pipes also preserve Linux profile line endings.
    global _connection
    if _connection is None or _connection.poll() is not None:
        _connection = subprocess.Popen(
            [*ssh_args(), "python3 -u -c " + shlex.quote(_EXECUTOR)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    _connection.stdin.write((json.dumps({"command": command, "data": data}) + "\n").encode())
    _connection.stdin.flush()
    line = _connection.stdout.readline()
    if not line:
        error = _connection.stderr.read().decode(errors="replace")[-2000:]
        close_guest()
        raise RuntimeError("VM connection failed: " + error)
    result = json.loads(line)
    if result.get("returncode") != 0:
        error = result.get("error") or base64.b64decode(result["stderr"]).decode(errors="replace")[-2000:]
        raise RuntimeError("VM verification failed: " + error)
    return base64.b64decode(result["stdout"]).decode().strip()


def main():
    guest("sudo test -f /var/lib/leroy-vm/ready")
    guest("cloud-init status --wait")
    assert guest("cat /sys/module/apparmor/parameters/enabled") == "Y"
    assert guest("systemctl is-active apparmor") == "active"
    assert guest("systemd-detect-virt") == "kvm"
    kernel = guest("uname -r")
    assert "microsoft" not in kernel.lower()
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "kernel": kernel,
        "os": guest(". /etc/os-release; printf '%s' \"$PRETTY_NAME\""),
        "virtualization": "kvm",
        "apparmor_enabled": True,
    }
    report["docker"] = json.loads(guest("sudo docker info --format '{{json .}}'"))["ServerVersion"]
    security = json.loads(guest("sudo docker info --format '{{json .SecurityOptions}}'"))
    assert any(option.split(",")[0] == "name=apparmor" for option in security)
    report["docker_security"] = security
    assert "Hello from Docker!" in guest(
        "sudo docker run --rm --security-opt apparmor=docker-default hello-world"
    )
    profile = """#include <tunables/global>
profile leroy-vm-proof flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>
  file,
  deny /tmp/leroy-apparmor-blocked r,
}
"""
    guest("sudo tee /etc/apparmor.d/leroy-vm-proof >/dev/null", data=profile)
    guest("sudo apparmor_parser -r /etc/apparmor.d/leroy-vm-proof")
    guest("printf test >/tmp/leroy-apparmor-blocked; cat /tmp/leroy-apparmor-blocked")
    denied = subprocess.run(
        [*ssh_args(), "sudo aa-exec -p leroy-vm-proof -- cat /tmp/leroy-apparmor-blocked"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert denied.returncode != 0 and "Permission denied" in denied.stderr, "AppArmor did not deny the read"
    guest(
        "sudo apparmor_parser -R /etc/apparmor.d/leroy-vm-proof; sudo rm /etc/apparmor.d/leroy-vm-proof /tmp/leroy-apparmor-blocked"
    )
    report["apparmor_enforcement"] = "unconfined read succeeded; confined read denied"
    graphato_profile = ROOT / ".sources/graphato/deployments/linux/host/graphato-server.apparmor"
    if graphato_profile.exists():
        guest(
            "sudo tee /etc/apparmor.d/graphato-server >/dev/null",
            data=graphato_profile.read_text(encoding="utf-8"),
        )
        guest("sudo apparmor_parser -r /etc/apparmor.d/graphato-server")
        status = json.loads(guest("sudo aa-status --json"))
        assert status["profiles"]["graphato-server"] == "enforce"
        report["original_graphato_profile"] = "loaded and enforced"
    info = json.loads(subprocess.check_output(["docker", "inspect", "leroy-linux-vm"], text=True))[0]
    assert not info["HostConfig"]["Privileged"]
    assert not any(m["Destination"] == "/var/run/docker.sock" for m in info["Mounts"])
    assert all(
        binding["HostIp"] == "127.0.0.1"
        for bindings in info["HostConfig"]["PortBindings"].values()
        for binding in bindings
    )
    # QEMU is the network proxy for its guest. A refused synthetic RFC1918 target
    # and the matching OUTPUT counter verify egress rejection without reaching a LAN service.
    probe = "import socket; s=socket.socket(); s.settimeout(3); print(s.connect_ex(('10.255.255.254',80)))"
    result = subprocess.check_output(
        ["docker", "exec", "leroy-linux-vm", "python3", "-c", probe], text=True
    ).strip()
    assert result == "111", result
    firewall = subprocess.check_output(
        ["docker", "exec", "leroy-linux-vm", "iptables", "-nvL", "OUTPUT"], text=True
    )
    assert all(network in firewall for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
    report["private_network_egress"] = "blocked in the QEMU network namespace"
    report["published_ports"] = {
        port: bindings for port, bindings in info["HostConfig"]["PortBindings"].items()
    }
    report["status"] = "passed"
    destination = ROOT / "test-results/vm"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
