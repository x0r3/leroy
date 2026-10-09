"""A diagnostic cannot certify truncated or failed Rust execution as complete success."""

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def parser(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    return importlib.import_module('compare_frozen_postdeploy_group')


def test_complete_failed_rust_execution_is_preserved(parser):
    rows = [{'type': 'suite', 'event': 'started', 'test_count': 2},
            {'type': 'test', 'event': 'ok', 'name': 'original::passed'},
            {'type': 'test', 'event': 'failed', 'name': 'original::failed'}]
    result = parser.rust_summary('\n'.join(map(json.dumps, rows)).encode())
    assert result['failed'] == 1 and result['failed_tests'] == ['original::failed']


def test_truncated_rust_execution_is_rejected(parser):
    with pytest.raises(AssertionError):
        parser.rust_summary(b'{"type":"suite","event":"started","test_count":1657}\n')


def test_empty_rust_execution_is_rejected(parser):
    with pytest.raises(AssertionError):
        parser.rust_summary(b'Fixture setup failed before any test ran\n')
