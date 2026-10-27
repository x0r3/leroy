"""Private file-backed test RAM must never accept arbitrary host paths."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('file_memory_launcher', Path(__file__).resolve().parents[1] / 'infra/vm/launch.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_default_launcher_never_accesses_a_memory_file(monkeypatch):
    monkeypatch.delenv('VM_MEMORY_FILE', raising=False)
    monkeypatch.setattr(launcher, 'validate_memory_file', lambda *a: pytest.fail('No memory file configured'))
    assert launcher.file_memory_options() is None


@pytest.mark.parametrize('path,size', [('/etc/foreign', '7168'), ('/vm-memory/ram.bin', '0'),
                                      ('/vm-memory/ram.bin', '32768')])
def test_unreviewed_path_or_size_is_rejected_before_opening(monkeypatch, path, size):
    monkeypatch.setenv('VM_MEMORY_FILE', path)
    monkeypatch.setenv('VM_MEMORY_MB', size)
    monkeypatch.setattr(launcher, 'validate_memory_file', lambda *a: pytest.fail('Invalid configuration must not access files'))
    with pytest.raises(ValueError):
        launcher.file_memory_options()


def test_file_backend_requires_private_file_and_shared_mapping(monkeypatch):
    monkeypatch.setenv('VM_MEMORY_FILE', '/vm-memory/ram.bin')
    monkeypatch.setenv('VM_MEMORY_MB', '7168')
    checked = []
    monkeypatch.setattr(launcher, 'validate_memory_file', lambda *args: checked.append(args))
    option = launcher.file_memory_options()
    assert checked == [('/vm-memory/ram.bin', 7 * 1024**3)]
    assert 'share=on' in option[1] and 'prealloc=off' in option[1] and 'dump=off' in option[1]


def test_default_disk_has_no_new_throttling(monkeypatch):
    monkeypatch.delenv('VM_DISK_READ_BPS', raising=False)
    monkeypatch.delenv('VM_DISK_WRITE_BPS', raising=False)
    assert launcher.disk_throttle_options() == ''


def test_guest_disk_throttle_keeps_the_qualified_rates(monkeypatch):
    monkeypatch.setenv('VM_DISK_READ_BPS', '134217728')
    monkeypatch.setenv('VM_DISK_WRITE_BPS', '33554432')
    assert launcher.disk_throttle_options() == ',bps_rd=134217728,bps_wr=33554432'


@pytest.mark.parametrize('read,write', [('134217728', None), (None, '33554432'), ('0', '0'),
                                     ('134217728', '33554433'), ('unlimited', '33554432')])
def test_partial_or_unqualified_disk_limits_fail_before_qemu(monkeypatch, read, write):
    for key, value in (('VM_DISK_READ_BPS', read), ('VM_DISK_WRITE_BPS', write)):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        launcher.disk_throttle_options()
