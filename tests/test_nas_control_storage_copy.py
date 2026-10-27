"""Regression for the actual shutil.copytree callback receiving string paths."""

import ast
import os
import pathlib
import shutil
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import migrate_nas_test_control_storage as storage  # noqa: E402


@pytest.mark.parametrize('path_type', [str, pathlib.Path])
def test_copy_callback_accepts_shutil_paths_and_preserves_bytes(tmp_path, path_type):
    source = tmp_path / 'original'
    target = tmp_path / 'copy'
    source.write_bytes(b'original test database bytes\x00\xff')
    owners = []
    flushes = []
    function = next(node for node in ast.parse(storage.PROGRAM).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'preserve_owner')
    environment = {'pathlib': pathlib, 'shutil': shutil,
                   'os': SimpleNamespace(chown=lambda path, uid, gid: owners.append((path, uid, gid)),
                       open=os.open, fsync=flushes.append, close=os.close, O_RDONLY=os.O_RDONLY)}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'copy callback', 'exec'), environment)
    result = environment['preserve_owner'](path_type(source), path_type(target))
    assert result == str(target) and target.read_bytes() == source.read_bytes()
    assert owners == [(target, source.stat().st_uid, source.stat().st_gid)]
    assert target.stat().st_mtime_ns == source.stat().st_mtime_ns
    # Linux permits fsync on the read-only descriptor; Windows does not.
    # The actual NAS migration verifies durability and ownership separately.
    assert len(flushes) == 1
