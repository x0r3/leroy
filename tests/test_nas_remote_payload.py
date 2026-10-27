"""Large sudo diagnostics must not exceed Windows argv or execute unverified bytes."""

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_release_vm as vm  # noqa: E402


def test_large_sudo_payload_is_uploaded_private_and_hash_bound(monkeypatch, tmp_path):
    monkeypatch.setattr(vm, 'LOCAL', tmp_path)
    program = '# diagnostic\n' + 'x = 1\n' * 6000
    uploaded = []
    scripts = []

    def upload(local, remote, credentials, *, timeout):
        assert local.read_text() == program and local.parent == tmp_path
        assert remote.startswith(vm.REMOTE + '/remote-input-') and remote.endswith('.py')
        uploaded.append(remote)

    def run(script, credentials, *, timeout, sudo):
        assert uploaded and sudo and len(script) < 2000
        assert hashlib.sha256(program.encode()).hexdigest() in script
        assert 'p.resolve()==p' in script and 'st_mode&0o077==0' in script
        scripts.append(script)
        return SimpleNamespace(returncode=0, stdout='verified', stderr='')

    monkeypatch.setattr(vm, 'upload_file', upload)
    monkeypatch.setattr(vm, 'run_script', run)
    assert vm.remote(program, sudo=True) == 'verified'
    assert len(scripts) == len(uploaded) == 1


def test_failed_upload_never_executes_partial_program(monkeypatch, tmp_path):
    monkeypatch.setattr(vm, 'LOCAL', tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError('upload failed')

    monkeypatch.setattr(vm, 'upload_file', fail)
    monkeypatch.setattr(vm, 'run_script', lambda *a, **kw: pytest.fail('Never execute an incomplete upload'))
    with pytest.raises(RuntimeError, match='upload failed'):
        vm.remote('pass\n' * 4000, sudo=True)
