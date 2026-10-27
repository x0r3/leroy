"""Run a reviewed script over OpenSSH, using local credentials and pinned host keys.

Credentials stay in .local/nas-ssh.json. OpenSSH obtains passwords through its
askpass pipe, never command arguments, the terminal, or a disabled host-key check.
This helper does not install keys, alter the NAS, or connect when merely imported.
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def credentials(path):
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if value.get("host") != "192.168.178.97" or value.get("port", 22) != 22:
        raise ValueError("This helper is restricted to the authorized NAS at 192.168.178.97:22")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}", value.get("username", "")):
        raise ValueError("Fill in the NAS SSH username in .local/nas-ssh.json")
    if not value.get("password") and not value.get("identity_file"):
        raise ValueError("Supply a password or identity_file in .local/nas-ssh.json")
    if "\n" in value.get("password", "") or "\r" in value.get("password", ""):
        raise ValueError("SSH askpass requires a single-line password")
    return value


def connection(credential_file):
    settings = credentials(credential_file)
    known_hosts = Path.home() / ".ssh/known_hosts"
    if not known_hosts.is_file():
        raise ValueError("A previously verified NAS host key in ~/.ssh/known_hosts is required")
    args = [
        "ssh",
        "-T",
        "-p",
        "22",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=" + str(known_hosts),
        "-o",
        "ConnectTimeout=10",
        "-o",
        "NumberOfPasswordPrompts=1",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
    ]
    env = dict(os.environ)
    if settings.get("identity_file"):
        args += ["-i", str(Path(settings["identity_file"]).expanduser()), "-o", "IdentitiesOnly=yes"]
    if settings.get("password"):
        helper = ROOT / ".local/nas-ssh-askpass.cmd"
        command = f'@"{sys.executable}" "{Path(__file__).resolve()}" --askpass\n'
        # Windows locks a running batch file. Reuse the unchanged helper so
        # independent read-only SSH requests do not race its execution.
        if not helper.exists() or helper.read_text() != command:
            helper.write_text(command)
        env.update(
            SSH_ASKPASS=str(helper),
            SSH_ASKPASS_REQUIRE="force",
            DISPLAY="leroy-nas",
            LEROY_NAS_SSH_CREDENTIALS=str(credential_file.resolve()),
        )
        if not settings.get("identity_file"):
            args += ["-o", "PreferredAuthentications=password", "-o", "PubkeyAuthentication=no"]
    else:
        args += ["-o", "BatchMode=yes"]
    return settings, args, env


def upload_file(local, remote, credential_file, *, timeout=600):
    """Copy only into this test stack's directory using the same verified host key."""
    if not re.fullmatch(r"/volume1/docker/leroy-nas-parity/[A-Za-z0-9_./-]+", remote):
        raise ValueError("Upload destination must be inside the owned NAS test directory")
    if ".." in remote.split("/"):
        raise ValueError("Parent path traversal is not allowed")
    import nas_native

    if nas_native.enabled():
        return nas_native.upload(local, remote, ROOT)
    settings, args, env = connection(credential_file)
    # UGOS restricts SFTP paths; stream through the already authorized SSH shell.
    # The final name only appears after the entire stream has been received.
    partial = shlex.quote(remote + ".upload")
    command = "umask 077; cat > " + partial + " && mv -- " + partial + " " + shlex.quote(remote)
    with Path(local).open("rb") as source:
        result = subprocess.run(
            [*args, settings["username"] + "@" + settings["host"], command],
            stdin=source,
            capture_output=True,
            env=env,
            timeout=timeout,
        )
    if result.returncode:
        diagnostic = result.stderr.decode("utf-8", errors="replace")
        if settings.get("password"):
            diagnostic = diagnostic.replace(settings["password"], "[REDACTED]")
        raise RuntimeError("NAS file upload failed: " + diagnostic[-1000:])


def run_script(script, credential_file, *, sudo=False, timeout=120):
    import nas_native

    if nas_native.enabled():
        return nas_native.run(script, ROOT, timeout=timeout)
    settings, args, env = connection(credential_file)
    command = "sh -s"
    stdin = script
    if sudo:
        if settings.get("password"):
            # Keep the password on stdin; the script body remains shell-quoted.
            command = "sudo -S -p '' sh -c " + shlex.quote(script)
            stdin = settings["password"] + "\n"
        else:
            command = "sudo -n sh -s"
    args += [settings["username"] + "@" + settings["host"], command]
    result = subprocess.run(
        args,
        # Binary stdin prevents Windows text mode from converting LF to CRLF.
        input=stdin.encode("utf-8"),
        capture_output=True,
        env=env,
        timeout=timeout,
    )
    for stream in ("stdout", "stderr"):
        value = getattr(result, stream).decode("utf-8", errors="replace")
        for name in ("password", "passphrase"):
            if settings.get(name):
                value = value.replace(settings[name], "[REDACTED]")
        setattr(result, stream, value)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", type=Path, default=ROOT / ".local/nas-ssh.json")
    parser.add_argument("--script", type=Path)
    parser.add_argument("--sudo", action="store_true")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--askpass", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.askpass:
        # Called only by OpenSSH; stdout is its private prompt-response pipe.
        settings = credentials(Path(os.environ["LEROY_NAS_SSH_CREDENTIALS"]))
        sys.stdout.write(settings["password"] + "\n")
        return
    if not args.script:
        parser.error("--script is required")
    try:
        result = run_script(
            args.script.read_text(encoding="utf-8"), args.credentials, sudo=args.sudo, timeout=args.timeout
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(str(exc) if isinstance(exc, ValueError) else type(exc).__name__) from None
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
