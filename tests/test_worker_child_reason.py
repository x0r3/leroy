"""A failed child must explain both its step and the parent run."""

import json
from pathlib import Path

import pytest

from leroy import worker
from leroy.schema import Pipeline, Step


@pytest.mark.parametrize('child_status', ['failed', 'succeeded'])
def test_child_outcome_reaches_parent_completion(monkeypatch, tmp_path, child_status):
    job = tmp_path / 'job'
    job.mkdir()
    pipeline = Pipeline(id='parent', name='Parent', steps=[
        Step(id='acceptance', name='Acceptance', action='child',
             options={'pipeline': 'child', 'wait': True})])
    (job / 'assignment.json').write_text(json.dumps({'id': 'parent-run', 'snapshot': pipeline.model_dump(),
                                                  'parameters': {}, 'commit': None}))
    (job / 'profile.json').write_text('{}')
    calls = []

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
                return [{'id': 'child-run', 'status': child_status}]
            return {'resumed': True}

    monkeypatch.setenv('LEROY_CONTROLLER', 'http://fixture')
    monkeypatch.setenv('LEROY_ATTEMPT_TOKEN', 'fixture-token')
    monkeypatch.setattr(worker, 'Reporter', Reporter)
    monkeypatch.setattr(worker, 'Path', lambda value: Path(tmp_path / str(value).lstrip('/')))
    monkeypatch.setattr(worker, 'maintain_lease', lambda *_: None)
    monkeypatch.setattr(worker.signal, 'signal', lambda *_: None)
    worker.main()
    completion, = [body for path, body in calls if path == '/complete']
    steps = [body for path, body in calls if path == '/steps/acceptance' and body['status'] == child_status]
    assert completion['status'] == child_status and steps
    if child_status == 'failed':
        assert completion['reason'] == 'acceptance: Child job did not succeed'
        assert steps[-1]['reason'] == 'Child job did not succeed'
    else:
        assert completion['reason'] == steps[-1]['reason'] == ''
