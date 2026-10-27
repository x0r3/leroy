"""The optional test-VM guard protects its own existing storage filesystem."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('vm_launcher', Path(__file__).resolve().parents[1] / 'infra/vm/launch.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_disabled_disk_guard_does_not_probe_other_filesystems(monkeypatch):
    monkeypatch.delenv('VM_MIN_DISK_FREE_MB', raising=False)
    monkeypatch.setattr(launcher.os, 'statvfs', lambda _: pytest.fail('Disabled guard must not query storage'),
                        raising=False)
    assert launcher.disk_pressure() is None


def test_disk_guard_checks_only_the_vm_filesystem_and_detects_reserve(monkeypatch):
    monkeypatch.setenv('VM_MIN_DISK_FREE_MB', '40960')

    def usage(path):
        assert path == '/vm'
        return SimpleNamespace(f_bavail=39 * 1024**2, f_frsize=1024)

    monkeypatch.setattr(launcher.os, 'statvfs', usage, raising=False)
    assert launcher.disk_pressure() == {'vm_disk_available_bytes': 39 * 1024**3,
                                        'minimum_vm_disk_available_bytes': 40 * 1024**3}


def test_disk_guard_accepts_available_reserve_and_rejects_negative_config(monkeypatch):
    monkeypatch.setenv('VM_MIN_DISK_FREE_MB', '40960')
    monkeypatch.setattr(launcher.os, 'statvfs', lambda _: SimpleNamespace(f_bavail=40 * 1024**2, f_frsize=1024),
                        raising=False)
    assert launcher.disk_pressure() is None
    monkeypatch.setenv('VM_MIN_DISK_FREE_MB', '-1')
    with pytest.raises(ValueError):
        launcher.disk_pressure()
