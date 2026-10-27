"""Own-kernel Ubuntu VM; the surrounding container only packages QEMU/KVM."""

import hashlib
import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import time
from pathlib import Path


def validate_memory_file(path, size):
    root = Path('/vm-memory')
    source = Path(path)
    if source != root / 'ram.bin' or source.resolve(strict=True) != source:
        raise ValueError('Only the dedicated private VM memory file is allowed')
    parent, info = root.stat(), source.stat()
    if (root.resolve(strict=True) != root or parent.st_uid != 0 or stat.S_IMODE(parent.st_mode) != 0o700
            or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
            or not stat.S_ISREG(info.st_mode) or info.st_size != size):
        raise ValueError('VM memory file ownership, permissions, or size differ')


def file_memory_options():
    path = os.environ.get('VM_MEMORY_FILE')
    if path is None:
        return None
    if path != '/vm-memory/ram.bin':
        raise ValueError('Unexpected VM memory file')
    size_mb = int(os.environ.get('VM_MEMORY_MB', '4096'))
    if not 512 <= size_mb <= 16384:
        raise ValueError('VM file memory size is outside the qualified range')
    validate_memory_file(path, size_mb * 1024**2)
    return ['-object', f'memory-backend-file,id=leroyram,size={size_mb}M,mem-path={path},'
            'share=on,prealloc=off,discard-data=on,dump=off']


def disk_throttle_options():
    read = os.environ.get('VM_DISK_READ_BPS')
    write = os.environ.get('VM_DISK_WRITE_BPS')
    if read is None and write is None:
        return ''
    if read is None or write is None:
        raise ValueError('Both guest disk throughput limits are required')
    if (read, write) != ('134217728', '33554432'):
        raise ValueError('Only the qualified 128/32 MiB/s guest disk limits are allowed')
    return f',bps_rd={read},bps_wr={write}'


def command(*args):
    subprocess.run(args, check=True)


def file_sha256(path):
    """Verify every byte and advise eviction of the consumed snapshot pages."""
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        offset = 0
        while block := stream.read(8 * 1024**2):
            digest.update(block)
            if hasattr(os, 'posix_fadvise'):
                try:
                    os.posix_fadvise(stream.fileno(), offset, len(block), os.POSIX_FADV_DONTNEED)
                except OSError:
                    # Advice can be unsupported. The complete hash remains mandatory.
                    pass
            offset += len(block)
    return digest.hexdigest()


def memory_floor():
    floors = {name: int(os.environ.get(variable, "0")) * 1024 for name, variable in (
        ("SwapFree", "VM_MIN_HOST_SWAP_MB"), ("MemAvailable", "VM_MIN_HOST_AVAILABLE_MB"))}
    if any(value < 0 for value in floors.values()):
        raise ValueError("Host memory floors cannot be negative")
    return floors


def memory_pressure(floors):
    if not any(floors.values()):
        return None
    memory = {line.split(":")[0]: int(line.split()[1])
              for line in Path("/proc/meminfo").read_text().splitlines()
              if line.startswith(("MemAvailable:", "SwapFree:"))}
    if any(memory[key] < floor for key, floor in floors.items() if floor):
        return {"host_memory_kib": memory, "minimum_host_memory_kib": floors}
    return None


def disk_pressure():
    minimum = int(os.environ.get("VM_MIN_DISK_FREE_MB", "0")) * 1024**2
    if minimum < 0:
        raise ValueError("Disk reserve cannot be negative")
    if minimum:
        info = os.statvfs("/vm")
        available = info.f_bavail * info.f_frsize
        if available < minimum:
            return {"vm_disk_available_bytes": available, "minimum_vm_disk_available_bytes": minimum}
    return None


def prepare():
    prepared = Path("/config/prepared.json")
    if prepared.exists():
        # An acceptance target can use an exported, already installed snapshot.
        # Each engine gets a new overlay; the immutable baseline stays read-only.
        manifest = json.loads(prepared.read_text())
        source = Path("/baseline/baseline.qcow2")
        identity = Path("/vm/prepared.json")
        if identity.exists():
            if json.loads(identity.read_text()) != manifest:
                raise RuntimeError("Prepared VM baseline changed; refusing to reuse its disk")
        else:
            if Path("/vm/system.qcow2").exists():
                raise RuntimeError("Unidentified prepared disk; refusing to replace it")
            if file_sha256(source) != manifest["sha256"]:
                raise RuntimeError("Prepared VM snapshot checksum mismatch")
            command("qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b",
                    str(source), "/vm/system.qcow2")
            identity.write_text(json.dumps(manifest, indent=2))
        for name in ("seed.img", "uefi-vars.fd"):
            destination = Path("/vm") / name
            if not destination.exists():
                shutil.copyfile(Path("/baseline") / name, destination)
        return
    manifest = json.loads(Path("/config/image.json").read_text())
    source = Path("/cache") / manifest["filename"]
    destination = Path("/vm/base.qcow2")
    if not destination.exists():
        if file_sha256(source) != manifest["sha256"]:
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
    floors = memory_floor()
    if memory_pressure(floors) or disk_pressure():
        raise RuntimeError("NAS resource reserve insufficient; no guest started")
    prepare()
    firewall()
    ssh_port = int(os.environ.get("VM_SSH_PORT", "2222"))
    if not 1024 <= ssh_port <= 65535:
        raise ValueError("VM SSH forwarding port must be between 1024 and 65535")
    disk_cache = os.environ.get("VM_DISK_CACHE", "none")
    if disk_cache not in {"none", "writeback"}:
        raise ValueError("VM disk cache must preserve flushes: none or writeback")
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
        f"file=/vm/system.qcow2,format=qcow2,if=virtio,cache={disk_cache},discard=unmap" + disk_throttle_options(),
        "-drive",
        "file=/vm/seed.img,format=raw,if=virtio,readonly=on",
        "-netdev",
        f"user,id=net0,net=10.90.0.0/24,ipv6=off,hostfwd=tcp:0.0.0.0:{ssh_port}-:22,hostfwd=tcp:0.0.0.0:8080-:80,hostfwd=tcp:0.0.0.0:8443-:443",
        "-device",
        "virtio-net-pci,netdev=net0",
        "-device",
        "virtio-rng-pci",
        "-device",
        "virtio-balloon-pci,free-page-reporting=on",
        "-display",
        "none",
        "-serial",
        "file:/vm/serial.log",
        "-monitor",
        "none",
        "-qmp",
        "unix:/run/qmp.sock,server=on,wait=off",
        "-trace",
        "enable=file_flush_fdatasync_failed,file=/vm/disk-errors.trace",
        "-sandbox",
        "on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny",
    ]
    if options := file_memory_options():
        args[args.index('-machine') + 1] += ',memory-backend=leroyram'
        args.extend(options)
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
    resource_guard = False
    while process.poll() is None:
        if stopping is None and (pressure := memory_pressure(floors) or disk_pressure()):
            resource_guard = True
            Path("/vm/resource-guard.json").write_text(json.dumps({"at": time.time(), **pressure}))
            print("NAS resource reserve reached; shutting down the owned test guest", flush=True)
            stop()
        grace = 45 if resource_guard else 210
        if stopping is not None and time.monotonic() - stopping > grace and not forced:
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
                "resource_guard_triggered": resource_guard,
            }
        )
    )
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
