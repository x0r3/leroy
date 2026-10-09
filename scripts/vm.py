"""Operate only the dedicated Leroy VM. No production Docker context is selected."""

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local/vm"


def compose_args():
    args = ["docker", "compose", "-f", "compose.vm.yaml"]
    if (LOCAL / "acceptance-enabled").exists():
        args += ["-f", "compose.vm.test.yaml"]
    if (LOCAL / "fresh.compose.yaml").exists():
        args += ["-f", str(LOCAL / "fresh.compose.yaml")]
    return args


def ssh_args():
    return [
        "ssh",
        "-i",
        str(LOCAL / "id_ed25519"),
        "-p",
        "2224",
        "-o",
        "UserKnownHostsFile=" + str(LOCAL / "known_hosts"),
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=4",
        "-o",
        "BatchMode=yes",
        "leroy-admin@127.0.0.1",
    ]


def main():
    parser = argparse.ArgumentParser(description="Manage the isolated Leroy Linux VM")
    parser.add_argument("action", choices=["ssh", "start", "stop", "status", "console", "snapshot"])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    compose = compose_args()
    if args.action == "ssh":
        command = [*ssh_args(), *args.command]
    elif args.action == "console":
        command = ["docker", "exec", "leroy-linux-vm", "tail", "-n", "60", "/vm/serial.log"]
    elif args.action == "snapshot":
        if len(args.command) != 1 or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", args.command[0]):
            parser.error("Specify one snapshot name (letters, numbers, dash, underscore or dot)")
        running = subprocess.check_output(
            ["docker", "inspect", "--format", "{{.State.Running}}", "leroy-linux-vm"], text=True
        ).strip()
        if running != "false":
            parser.error("Stop the VM cleanly before taking a disk snapshot")
        command = [
            *compose,
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "qemu-img",
            "vm",
            "snapshot",
            "-c",
            args.command[0],
            "/vm/system.qcow2",
        ]
    else:
        if args.action == "stop":
            running = subprocess.check_output(
                ["docker", "inspect", "--format", "{{.State.Running}}", "leroy-linux-vm"], text=True
            ).strip()
            if running == "true":
                # Drain the test application before starting system shutdown.
                # Cloud guests may not handle ACPI buttons reliably.
                try:
                    request = subprocess.run(
                        [
                            *ssh_args(),
                            "sudo sh -c 'if systemctl is-enabled --quiet leroy-test-graphato.service; then systemctl stop leroy-test-graphato.service || exit 1; fi; systemctl poweroff --no-block'",
                        ],
                        capture_output=True,
                        timeout=190,
                    )
                    if request.returncode == 255:
                        print("Guest SSH unavailable; using the QMP shutdown fallback", flush=True)
                    elif request.returncode:
                        raise SystemExit("Guest refused clean shutdown; VM remains running")
                except subprocess.TimeoutExpired:
                    raise SystemExit("Guest shutdown preparation timed out; VM remains running") from None
        operation = {"start": ["up", "-d"], "stop": ["stop"], "status": ["ps"]}[args.action]
        command = [*compose, *operation]
    raise SystemExit(subprocess.call(command, cwd=ROOT))


if __name__ == "__main__":
    main()
