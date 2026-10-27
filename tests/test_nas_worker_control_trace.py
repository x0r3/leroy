"""The process trace must sample the interpreter, never Docker's init wrapper."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from nas_worker_control_trace import PROGRAM, worker_interpreter  # noqa: E402


@pytest.mark.parametrize('executable', [b'python', b'python3', b'/opt/venv/bin/python3.13'])
def test_recognizes_actual_worker_interpreter(executable):
    assert worker_interpreter([executable, b'-m', b'leroy.worker', b''])


@pytest.mark.parametrize('argv', [[], [b'python'],
    [b'/sbin/docker-init', b'--', b'python', b'-m', b'leroy.worker', b''],
    [b'python', b'-c', b'print(1)', b'-m', b'leroy.worker', b''],
    [b'python', b'-m', b'another.module', b'']])
def test_rejects_init_wrapper_and_unrelated_processes(argv):
    assert not worker_interpreter(argv)


def test_remote_payload_uses_the_same_interpreter_selection():
    compile(PROGRAM, 'owned-worker-process-observer', 'exec')
    assert 'if worker_interpreter(argv):python=p;break' in PROGRAM
