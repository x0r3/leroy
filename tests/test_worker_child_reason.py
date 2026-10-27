"""A failed child must explain both its step and the parent run."""

import json
import threading
from pathlib import Path

import pytest

from leroy import worker
from leroy.schema import Pipeline, Step


@pytest.mark.parametrize('child_status,lose_lease', [('failed', False), ('succeeded', False), ('running', True)])
def test_child_outcome_reaches_parent_completion(monkeypatch, tmp_path, child_status, lose_lease):
    job = tmp_path / 'job'
    job.mkdir()
    pipeline = Pipeline(id='parent', name='Parent', steps=[
        Step(id='acceptance', name='Acceptance', action='child',
             options={'pipeline': 'child', 'wait': True})])
    (job / 'assignment.json').write_text(json.dumps({'id': 'parent-run', 'snapshot': pipeline.model_dump(),
                                                  'parameters': {}, 'commit': None}))
    (job / 'profile.json').write_text('{}')
    calls = []
    lease_control, lease_ready = {}, threading.Event()

    def monitor(_send, _stop, cancelled, reason):
        lease_control.update(cancelled=cancelled, reason=reason)
        lease_ready.set()

    class Reporter:
        def __init__(self, *_):
            pass

        def heartbeat(self):
            return {'cancel': False}

        def send(self, path, *, body=None, **_):
            calls.append((path, body))
            if path == '/children/child':
                return {'id': 'child-run', 'status': 'queued'}
            if path == '/children':
                if lose_lease:
                    assert lease_ready.wait(1)
                    lease_control['reason'][0] = 'Controller lease could not be renewed (last failure: ReadTimeout)'
                    lease_control['cancelled'].set()
                return [{'id': 'child-run', 'status': child_status}]
            return {'resumed': True}

    monkeypatch.setenv('LEROY_CONTROLLER', 'http://fixture')
    monkeypatch.setenv('LEROY_ATTEMPT_TOKEN', 'fixture-token')
    monkeypatch.setattr(worker, 'Reporter', Reporter)
    monkeypatch.setattr(worker, 'Path', lambda value: Path(tmp_path / str(value).lstrip('/')))
    monkeypatch.setattr(worker, 'maintain_lease', monitor)
    monkeypatch.setattr(worker.signal, 'signal', lambda *_: None)
    worker.main()
    completion, = [body for path, body in calls if path == '/complete']
    expected_status = 'cancelled' if lose_lease else child_status
    steps = [body for path, body in calls if path == '/steps/acceptance' and body['status'] == expected_status]
    assert completion['status'] == expected_status and steps
    if lose_lease:
        assert completion['reason'] == steps[-1]['reason'] == lease_control['reason'][0]
        assert steps[-1]['outputs']['acceptance_result'] == 'running'
    elif child_status == 'failed':
        assert completion['reason'] == 'acceptance: Child job did not succeed'
        assert steps[-1]['reason'] == 'Child job did not succeed'
    else:
        assert completion['reason'] == steps[-1]['reason'] == ''
