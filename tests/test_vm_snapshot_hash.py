"""Bounded cache advice must not skip snapshot bytes or change verification."""

import hashlib
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('snapshot_launcher', Path(__file__).resolve().parents[1] / 'infra/vm/launch.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_snapshot_hash_covers_chunk_boundaries_and_preserves_file(monkeypatch, tmp_path):
    path = tmp_path / 'snapshot'
    data = b'A' * (8 * 1024**2) + b'B' * 37
    path.write_bytes(data)
    hints = []
    monkeypatch.setattr(launcher.os, 'POSIX_FADV_DONTNEED', 4, raising=False)
    monkeypatch.setattr(launcher.os, 'posix_fadvise', lambda fd, offset, size, hint: hints.append((offset, size, hint)), raising=False)
    assert launcher.file_sha256(path) == hashlib.sha256(data).hexdigest()
    assert hints == [(0, 8 * 1024**2, 4), (8 * 1024**2, 37, 4)]
    assert path.read_bytes() == data


@pytest.mark.parametrize('unsupported', [False, True])
def test_cache_advice_is_optional_but_hash_is_not(monkeypatch, tmp_path, unsupported):
    path = tmp_path / 'snapshot'
    path.write_bytes(b'complete immutable snapshot')
    if unsupported:
        monkeypatch.delattr(launcher.os, 'posix_fadvise', raising=False)
    else:
        def reject(*args):
            raise OSError('Advisory interface unavailable')
        monkeypatch.setattr(launcher.os, 'posix_fadvise', reject, raising=False)
        monkeypatch.setattr(launcher.os, 'POSIX_FADV_DONTNEED', 4, raising=False)
    assert launcher.file_sha256(path) == hashlib.sha256(path.read_bytes()).hexdigest()
