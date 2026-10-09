"""Own-kernel Ubuntu VM; the surrounding container only packages QEMU/KVM."""

import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path


def command(*args):
    subprocess.run(args, check=True)


def prepare():
    manifest = json.loads(Path("/config/image.json").read_text())
    source = Path("/cache") / manifest["filename"]
    destination = Path("/vm/base.qcow2")
    if not destination.exists():
        with source.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != manifest["sha256"]:
                raise RuntimeError("Ubuntu cloud image checksum mismatch")
        temporary = destination.with_suffix(".copying")
        shutil.copyfile(source, temporary)
        temporary.replace(destination)
        Path("/vm/image.json").write_text(json.dumps(manifest, indent=2))
    elif json.loads(Path("/vm/image.json").read_text())["sha256"] != manifest["sha256"]:
        raise RuntimeError("Existing VM uses another base image; refusing to replace its disk")
    if not Path("/vm/system.qcow2").exists():
        command(
            "qemu-img",
            "create",
            "-f",
            "qcow2",
            "-F",
            "qcow2",
            "-b",
            str(destination),
            "/vm/system.qcow2",
            "64G",
        )
    if not Path("/vm/seed.img").exists():
        command("cloud-localds", "/vm/seed.img", "/config/user-data", "/config/meta-data")
    if not Path("/vm/uefi-vars.fd").exists():
        shutil.copyfile("/usr/share/OVMF/OVMF_VARS_4M.fd", "/vm/uefi-vars.fd")


def firewall():
    # These rules apply only to this container's network namespace. QEMU user
    # networking originates guest traffic here, so a guest cannot reach the LAN,
    # Windows host services or other Docker projects, even after changing guest rules.
    command("iptables", "-A", "OUTPUT", "-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "ACCEPT")
    command("iptables", "-A", "OUTPUT", "-o", "lo", "-j", "ACCEPT")
    for network in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
        "100.64.0.0/10",
        "11.254.254.254/32",
    ):
        command("iptables", "-A", "OUTPUT", "-d", network, "-j", "REJECT")


def powerdown():
    with socket.socket(socket.AF_UNIX) as stream:
        stream.settimeout(5)
        stream.connect("/run/qmp.sock")
        response = stream.makefile("rb")
        response.readline()
        stream.sendall(b'{"execute":"qmp_capabilities"}\n')
        response.readline()
        stream.sendall(b'{"execute":"system_powerdown"}\n')
        # Keep the monitor connected until QEMU has actually accepted the
        # command; asynchronous monitor events can precede its response.
        while True:
            line = response.readline()
            if not line:
                raise OSError("QMP closed before acknowledging powerdown")
            message = json.loads(line)
            if "error" in message:
                raise OSError("QMP rejected powerdown")
            if "return" in message:
                break


def main():
    prepare()
    firewall()
    args = [
        "qemu-system-x86_64",
        "-name",
        "leroy-ubuntu-24.04",
        "-machine",
        "q35,accel=kvm",
        "-cpu",
        "host",
        "-smp",
        os.environ.get("VM_CPUS", "4"),
        "-m",
        os.environ.get("VM_MEMORY_MB", "4096"),
        "-drive",
        "if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd",
        "-drive",
        "if=pflash,format=raw,file=/vm/uefi-vars.fd",
        "-drive",
        "file=/vm/system.qcow2,format=qcow2,if=virtio,cache=none,discard=unmap",
        "-drive",
        "file=/vm/seed.img,format=raw,if=virtio,readonly=on",
        "-netdev",
        "user,id=net0,net=10.90.0.0/24,ipv6=off,hostfwd=tcp:0.0.0.0:2222-:22,hostfwd=tcp:0.0.0.0:8080-:80,hostfwd=tcp:0.0.0.0:8443-:443",
        "-device",
        "virtio-net-pci,netdev=net0",
        "-device",
        "virtio-rng-pci",
        "-display",
        "none",
        "-serial",
        "file:/vm/serial.log",
        "-monitor",
        "none",
        "-qmp",
        "unix:/run/qmp.sock,server=on,wait=off",
        "-sandbox",
        "on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny",
    ]
    stopping = None

    def stop(*_):
        nonlocal stopping
        if stopping is None:
            stopping = time.monotonic()
            try:
                powerdown()
            except OSError as error:
                print("Guest ACPI shutdown request failed: " + str(error), flush=True)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(
        "Starting Ubuntu VM with KVM, 64 GiB virtual disk, loopback SSH and blocked private-network egress",
        flush=True,
    )
    process = subprocess.Popen(args)
    forced = False
    while process.poll() is None:
        if stopping is not None and time.monotonic() - stopping > 210 and not forced:
            forced = True
            print("Guest shutdown timed out; forcing QEMU termination", flush=True)
            process.terminate()
        time.sleep(1)
    Path("/vm/shutdown.json").write_text(
        json.dumps(
            {
                "finished_at": time.time(),
                "forced": forced,
                "qemu_exit_code": process.returncode,
            }
        )
    )
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
