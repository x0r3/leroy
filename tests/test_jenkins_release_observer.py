"""A failed checkout cannot leave the observer waiting for nonexistent children."""

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
observer = importlib.import_module('compare_frozen_release_cpu_eight')
COMMIT = 'b' * 40
BUILDS = {'graphato-release-acceptance': 16, 'graphato-postdeploy-web': 19, 'graphato-postdeploy-quality': 17}


@pytest.mark.parametrize('child_initially_active', [False, True])
def test_terminal_parent_retains_original_attempt_and_waits_only_for_real_work(tmp_path, monkeypatch, child_initially_active):
    marker = tmp_path / 'jenkins-start.json'
    marker.write_text(json.dumps({'builds': BUILDS, 'production_guard_before': 'retained-boundary.json'}))
    original = marker.read_bytes()
    polling_round = 0
    reads, sleeps, qualifications = [], [], []

    def state(job, number):
        nonlocal polling_round
        assert number == BUILDS[job]
        reads.append((job, number))
        if job == 'graphato-release-acceptance':
            return {'number': number, 'started': True, 'building': False, 'result': 'FAILURE'}
        if job == 'graphato-postdeploy-web' and child_initially_active:
            return {'number': number, 'started': True, 'building': polling_round == 0, 'result': None if polling_round == 0 else 'FAILURE'}
        return {'number': number, 'started': False}

    def sleep(seconds):
        nonlocal polling_round
        assert seconds == 20 and polling_round == 0
        sleeps.append(seconds)
        polling_round += 1

    def api(path, *args, **kwargs):
        assert path == '/queue/api/json?tree=items[id]' and not args and not kwargs
        return {'text': json.dumps({'items': []})}

    def forbidden(*args, **kwargs):
        pytest.fail('Observing this existing original run must not dispatch, cancel or reset CI')

    monkeypatch.setattr(observer.group, 'original_jenkins_state', state)
    monkeypatch.setattr(observer, 'jenkins_api', api)
    monkeypatch.setattr(observer.time, 'sleep', sleep)
    monkeypatch.setattr(observer, 'finish', lambda folder, phase, before: qualifications.append((phase, before)))
    monkeypatch.setattr(observer, 'inner', forbidden)
    monkeypatch.setattr(observer.group, 'restore', forbidden)
    monkeypatch.setattr(observer.group, 'target', forbidden)
    monkeypatch.setattr(observer.group, 'collect_jenkins', forbidden)
    monkeypatch.setattr(observer, 'start_jenkins', forbidden)
    with pytest.raises(RuntimeError, match='parent finished before all child jobs started'):
        observer.jenkins(tmp_path, COMMIT, 'retained-baseline')
    assert marker.read_bytes() == original
    proof = json.loads((tmp_path / 'jenkins-incomplete-release-tree.json').read_text())
    assert proof['original_parent_number'] == 16 and proof['original_ci_restarted'] is False
    assert proof['missing_original_pipelines'] == (['graphato-postdeploy-quality'] if child_initially_active else ['graphato-postdeploy-quality', 'graphato-postdeploy-web'])
    assert len(reads) == (6 if child_initially_active else 3)
    assert len(sleeps) == int(child_initially_active)
    assert qualifications == [('jenkins', 'retained-boundary.json')]
