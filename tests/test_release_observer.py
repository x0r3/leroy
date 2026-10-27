"""Observation retries retain an existing CI attempt and authenticated client."""

import importlib
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
observer = importlib.import_module('compare_frozen_release_cpu_eight')
RUN = 'a' * 32
COMMIT = 'b' * 40


class ExistingRunAPI:
    def __init__(self, statuses):
        self.statuses = iter(statuses)
        self.requests = []
        self.closed = 0

    def get(self, path):
        assert path == '/api/runs/' + RUN
        self.requests.append(path)
        status = next(self.statuses)
        if isinstance(status, Exception):
            raise status
        return httpx.Response(200, request=httpx.Request('GET', 'http://isolated.invalid' + path),
                              json={'id': RUN, 'commit': COMMIT, 'parent_id': None,
                                    'pipeline_id': 'graphato-release-acceptance',
                                    'children': [], 'status': status})

    def post(self, *args, **kwargs):
        pytest.fail('Observations must never dispatch or cancel an original CI attempt')

    def close(self):
        self.closed += 1


@pytest.fixture
def configure(monkeypatch):
    monkeypatch.setattr(observer.time, 'sleep', lambda seconds: None)

    def factory(api, initial_failure=None):
        calls = []

        def client():
            calls.append(True)
            if initial_failure is not None and len(calls) == 1:
                raise initial_failure
            return api

        monkeypatch.setattr(observer, 'client', client)
        return calls

    return factory


def test_reuses_authenticated_client_across_existing_run_polls(tmp_path, configure):
    api = ExistingRunAPI(['queued', 'running', 'interrupted'])
    calls = configure(api)
    runs, state = observer.observe_leroy_runs(tmp_path, RUN, COMMIT)
    assert len(calls) == 1 and api.closed == 1
    assert api.requests == ['/api/runs/' + RUN] * 3
    assert runs[0]['status'] == 'interrupted'
    assert state['graphato-release-acceptance']['id'] == RUN


def test_read_timeout_keeps_client_and_original_run_and_redacts_exception(tmp_path, configure):
    api = ExistingRunAPI(['running', httpx.ReadTimeout('private-token-in-url'), 'interrupted'])
    calls = configure(api)
    observer.observe_leroy_runs(tmp_path, RUN, COMMIT)
    assert len(calls) == 1 and api.closed == 1
    text = (tmp_path / 'leroy-observation-errors.jsonl').read_text()
    event = json.loads(text)
    assert event['original_parent'] == RUN and event['original_ci_restarted'] is False
    assert event['observation_error'] == 'ReadTimeout' and 'private-token' not in text


def test_initial_auth_transport_failure_retries_observation_only(tmp_path, configure):
    api = ExistingRunAPI(['interrupted'])
    calls = configure(api, httpx.RemoteProtocolError('private-auth-response'))
    observer.observe_leroy_runs(tmp_path, RUN, COMMIT)
    assert len(calls) == 2 and api.requests == ['/api/runs/' + RUN] and api.closed == 1
    text = (tmp_path / 'leroy-observation-errors.jsonl').read_text()
    assert json.loads(text)['observation_error'] == 'RemoteProtocolError'
    assert 'private-auth-response' not in text


def test_expired_session_renews_authentication_without_restarting_ci(tmp_path, monkeypatch, configure):
    response = httpx.Response(401, request=httpx.Request('GET', 'http://isolated.invalid'))
    expired = ExistingRunAPI([httpx.HTTPStatusError('private-auth-body', request=response.request, response=response)])
    renewed = ExistingRunAPI(['interrupted'])
    clients = iter([expired, renewed])
    monkeypatch.setattr(observer, 'client', lambda: next(clients))
    observer.observe_leroy_runs(tmp_path, RUN, COMMIT)
    assert expired.closed == renewed.closed == 1
    assert expired.requests == renewed.requests == ['/api/runs/' + RUN]
    text = (tmp_path / 'leroy-observation-errors.jsonl').read_text()
    assert json.loads(text)['observation_error'] == 'HTTP401' and 'private-auth-body' not in text


def test_forbidden_observation_fails_without_reauthentication_or_ci_dispatch(tmp_path, configure):
    response = httpx.Response(403, request=httpx.Request('GET', 'http://isolated.invalid'))
    api = ExistingRunAPI([httpx.HTTPStatusError('Forbidden', request=response.request, response=response)])
    calls = configure(api)
    with pytest.raises(httpx.HTTPStatusError):
        observer.observe_leroy_runs(tmp_path, RUN, COMMIT)
    assert len(calls) == 1 and api.closed == 1
