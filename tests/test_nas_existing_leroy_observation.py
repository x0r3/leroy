"""Administrative SSH loss must not abort observation of an already dispatched run."""
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import compare_frozen_postdeploy_group as group  # noqa: E402


def test_http_read_retry_never_reenters_ssh_admission_or_dispatch(monkeypatch, tmp_path):
    run_id, commit = 'a' * 32, 'b' * 40
    parameters = {'CHECK_GROUP': 'server-test', 'RELEASE_COMMIT': commit}
    (tmp_path / 'leroy-start.json').write_text(json.dumps({'id': run_id, 'production_guard_before': 'before'}))
    (tmp_path / 'leroy-target-before.json').write_text(json.dumps({'manifest': {'commit': commit}}))
    results = iter(['running', httpx.ReadTimeout('private-url-token'), 'interrupted'])
    calls = []

    class API:
        def get(self, path):
            assert path == '/api/runs/' + run_id
            calls.append(path)
            result = next(results)
            if isinstance(result, Exception):
                raise result
            return httpx.Response(200, request=httpx.Request('GET', 'http://test.invalid' + path), json={
                'id': run_id, 'commit': commit, 'pipeline_id': 'quality', 'parameters': parameters,
                'status': result, 'steps': []})

        def post(self, *args, **kwargs):
            pytest.fail('Never dispatch a known run again')

        def close(self):
            pass

    for name in ('require_current_jenkins', 'inner', 'restore', 'begin', 'start_jenkins'):
        monkeypatch.setattr(group, name, lambda *a, **kw: pytest.fail('No repeated SSH admission or dispatch'))
    monkeypatch.setattr(group, 'client', API)
    monkeypatch.setattr(group.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(group, 'collect_artifacts', lambda *a: None)
    monkeypatch.setattr(group, 'target', lambda *a: {'manifest': {'commit': commit}})
    finished = []
    monkeypatch.setattr(group, 'finish', lambda *a: finished.append(a))
    with pytest.raises(httpx.ReadTimeout):
        group.execute_engine(tmp_path, 'leroy', commit, 'quality', parameters, 'baseline')
    group.execute_engine(tmp_path, 'leroy', commit, 'quality', parameters, 'baseline')
    assert calls == ['/api/runs/' + run_id] * 3
    assert json.loads((tmp_path / 'leroy-run.json').read_text())['status'] == 'interrupted'
    assert finished == [(tmp_path, 'leroy', 'before')]
