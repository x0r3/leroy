"""Native mode is explicit, has no SSH/password path, and refuses other hosts."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_native  # noqa: E402
import nas_ssh  # noqa: E402


def test_not_enabled_by_default(monkeypatch):
    monkeypatch.delenv('LEROY_NAS_NATIVE', raising=False)
    assert not nas_native.enabled()


def test_native_execution_does_not_read_ssh_credentials(monkeypatch):
    monkeypatch.setenv('LEROY_NAS_NATIVE', '1')
    monkeypatch.setattr(nas_native, 'validate', lambda root: None)
    monkeypatch.setattr(nas_ssh, 'connection', lambda *a: pytest.fail('No administrative SSH'))
    calls = []

    def execute(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, b'{"ok":true}\n', b'')

    monkeypatch.setattr(nas_native.subprocess, 'run', execute)
    response = nas_ssh.run_script('read_only_probe()\n', Path('no-credentials'), sudo=True, timeout=7)
    assert response.stdout == '{"ok":true}\n'
    assert calls == [(['/bin/sh', '-s'], {'input': b'read_only_probe()\n', 'capture_output': True, 'timeout': 7})]


def test_refuses_non_linux_and_unrelated_workspaces(monkeypatch, tmp_path):
    monkeypatch.setattr(nas_native.sys, 'platform', 'win32')
    with pytest.raises(AssertionError):
        nas_native.validate(tmp_path)
    monkeypatch.setattr(nas_native.sys, 'platform', 'linux')
    monkeypatch.setattr(nas_native.os, 'geteuid', lambda: 0, raising=False)
    with pytest.raises(AssertionError):
        nas_native.validate(tmp_path)


def test_native_upload_keeps_destination_boundary(monkeypatch):
    monkeypatch.setenv('LEROY_NAS_NATIVE', '1')
    monkeypatch.setattr(nas_native, 'upload', lambda *a: pytest.fail('Reject before upload'))
    for destination in ('/etc/test', '/volume1/docker/leroy-nas-parity/../outside'):
        with pytest.raises(ValueError):
            nas_ssh.upload_file(Path('source'), destination, Path('no-credentials'))
