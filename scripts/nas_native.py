"""Explicit local transport for the root-owned NAS acceptance workspace.

Only the operator uses this transport. Original CI execution SSH and Leroy
heartbeats are unchanged. Windows and arbitrary Linux directories cannot opt in.
"""
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

OWNER = Path('/volume1/docker/leroy-nas-parity')


def enabled():
    return os.environ.get('LEROY_NAS_NATIVE') == '1'


def validate(root):
    assert sys.platform == 'linux' and os.geteuid() == 0, 'Native acceptance requires NAS root'
    assert root == root.resolve() and root.name == 'workspace'
    assert root.parent.parent == OWNER and re.fullmatch(r'acceptance-operator-[0-9]{8}-[a-z0-9-]{1,32}', root.parent.name)
    assert (OWNER / '.leroy-owned').is_file()
    identity = root.parent / 'native-identity.json'
    assert identity.resolve() == identity and identity.stat().st_uid == 0
    assert stat.S_IMODE(identity.stat().st_mode) == 0o600
    value = json.loads(identity.read_text())
    assert value['root'] == str(root) and value['hostname'] == socket.gethostname()
    assert value['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    return value


def run(script, root, *, timeout):
    validate(root)
    result = subprocess.run(['/bin/sh', '-s'], input=script.encode('utf-8'),
                            capture_output=True, timeout=timeout)
    result.stdout = result.stdout.decode('utf-8', errors='replace')
    result.stderr = result.stderr.decode('utf-8', errors='replace')
    return result


def upload(source, destination, root):
    validate(root)
    source, destination = Path(source), Path(destination)
    assert source.resolve().is_relative_to(root) and source.is_file()
    assert destination.parent.resolve() == destination.parent
    assert destination.is_relative_to(OWNER) and not destination.is_symlink()
    descriptor, temporary = tempfile.mkstemp(prefix=destination.name + '.native-', dir=destination.parent)
    try:
        with os.fdopen(descriptor, 'wb') as target, source.open('rb') as incoming:
            os.fchmod(target.fileno(), 0o600)
            shutil.copyfileobj(incoming, target, 1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, destination)
        directory = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
