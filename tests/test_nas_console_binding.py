"""A console layer must preserve the previously qualified controller engine."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_console_binding as console  # noqa: E402


def test_historical_admission_still_requires_its_original_controller():
    assert console.qualified_controller_image('old', None) == 'old'
    assert console.qualified_controller_image('old', {'attempt': 'v'}) == 'old'


def test_new_layer_requires_exact_previously_qualified_engine(monkeypatch, tmp_path):
    monkeypatch.setattr(console.vm, 'ROOT', tmp_path)
    monkeypatch.setattr(console, 'binding', lambda: {'controller_image': 'new'})
    target = tmp_path / 'test-results/nas-parity/followup/console-queue-20261017/deployment/deployment-proof.json'
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({'previous_controller_image': 'old'}))
    approval = {'attempt': 'w', 'console_logging_binding': {'controller_image': 'new'}}
    assert console.qualified_controller_image('old', approval) == 'new'
    with pytest.raises(AssertionError):
        console.qualified_controller_image('different-engine', approval)
    approval['console_logging_binding'] = {'controller_image': 'unqualified'}
    with pytest.raises(AssertionError):
        console.qualified_controller_image('old', approval)
