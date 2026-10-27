"""The corrective test environment must be explicit and precede application start."""

import json
import os
import pathlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from nas_vm_postgres_init import PROGRAM  # noqa: E402


@pytest.fixture
def guest(tmp_path, monkeypatch):
    real = pathlib.Path
    (tmp_path / 'ready').touch()

    def path(value):
        if str(value).startswith('/var/lib/leroy-vm'):
            return tmp_path / str(value).removeprefix('/var/lib/leroy-vm').lstrip('/')
        return real(value)

    running = [False] * 4

    def read(args, **kwargs):
        assert kwargs == {'text': True}
        if args == ['systemd-detect-virt']:
            return 'kvm\n'
        if args[:3] == ['docker', 'ps', '-aq']:
            return ' '.join(str(i) for i in range(4))
        assert args == ['docker', 'inspect', '0', '1', '2', '3']
        return json.dumps([{'State': {'Running': value}} for value in running])

    monkeypatch.setattr(pathlib, 'Path', path)
    monkeypatch.setattr(os, 'geteuid', lambda: 0, raising=False)
    monkeypatch.setattr(subprocess, 'check_output', read)
    return tmp_path, running


def test_override_is_staged_before_services_start_and_is_idempotent(guest):
    root, _ = guest
    exec(compile(PROGRAM, 'isolated-postgres-init', 'exec'), {})
    target = root / 'postgres-init.override.json'
    expected = {'services': {'postgres': {'init': True}}}
    assert json.loads(target.read_text()) == expected
    before = target.stat().st_mtime_ns
    exec(compile(PROGRAM, 'isolated-postgres-init', 'exec'), {})
    assert target.stat().st_mtime_ns == before


def test_override_cannot_restart_a_running_baseline(guest):
    root, running = guest
    running[0] = True
    with pytest.raises(AssertionError, match='before the clean baseline'):
        exec(compile(PROGRAM, 'isolated-postgres-init', 'exec'), {})
    assert not (root / 'postgres-init.override.json').exists()


def test_different_existing_override_is_retained_and_rejected(guest):
    root, _ = guest
    target = root / 'postgres-init.override.json'
    target.write_text('{"services":{"postgres":{"init":false}}}')
    original = target.read_bytes()
    with pytest.raises(AssertionError):
        exec(compile(PROGRAM, 'isolated-postgres-init', 'exec'), {})
    assert target.read_bytes() == original
