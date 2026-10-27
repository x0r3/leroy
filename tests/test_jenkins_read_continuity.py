"""Unavailable observations must never cancel or redispatch original CI work."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import compare_frozen_postdeploy_group as group  # noqa: E402
import compare_frozen_release_cpu_eight as release  # noqa: E402

JOB = 'graphato-postdeploy-quality'
COMMIT = 'a' * 40


@pytest.mark.parametrize('failure', [
    subprocess.TimeoutExpired('secret command', 60, stderr='secret payload'),
    OSError('secret transport details'),
    SimpleNamespace(returncode=255, stderr='secret SSH error', stdout=''),
    SimpleNamespace(returncode=0, stderr='', stdout='secret incomplete JSON'),
])
def test_transport_and_partial_reads_are_uncertainty_without_secret_output(monkeypatch, failure):
    def read(*args, **kwargs):
        if isinstance(failure, Exception):
            raise failure
        return failure

    monkeypatch.setattr(group, 'run_script', read)
    with pytest.raises(group.JenkinsReadUnavailable) as caught:
        group.original_jenkins_state(JOB, 28)
    assert 'secret' not in str(caught.value)


@pytest.mark.parametrize('state', [
    {'number': 29, 'started': True, 'building': True},
    {'number': 28, 'started': 'true', 'building': True},
    {'number': 28, 'started': True, 'building': False, 'result': None},
    {'number': 28, 'started': True, 'building': False, 'result': 'unexpected'},
])
def test_unconfirmed_or_mismatched_terminal_state_cannot_finish_observation(monkeypatch, state):
    monkeypatch.setattr(group, 'jenkins_read', lambda *a, **kw: {JOB: state})
    with pytest.raises(group.JenkinsReadUnavailable, match='InvalidStatus'):
        group.original_jenkins_state(JOB, 28)


def test_existing_original_job_survives_status_and_artifact_timeouts(tmp_path, monkeypatch):
    marker = tmp_path / 'jenkins-start.json'
    marker.write_text(json.dumps({'number': 28, 'production_guard_before': 'original-boundary'}))
    original_marker = marker.read_bytes()
    manifest = {'commit': COMMIT, 'runtime': 'original-unpatched-image'}
    (tmp_path / 'jenkins-target-before.json').write_text(json.dumps({'manifest': manifest}))
    reads, collections, sleeps, boundaries = [], [], [], []

    def forbidden(*args, **kwargs):
        pytest.fail('Read recovery must not dispatch, restore, reset or cancel CI')

    def status(job, number):
        reads.append((job, number))
        if len(reads) == 1:
            raise group.JenkinsReadUnavailable('TimeoutExpired')
        return {'number': number, 'started': True, 'building': len(reads) == 2,
                'result': None if len(reads) == 2 else 'SUCCESS'}

    def collect(folder, job, number, commit):
        collections.append((job, number, commit))
        if len(collections) == 1:
            raise group.JenkinsReadUnavailable('SSHExit')
        (folder / 'jenkins-build.json').write_text(json.dumps({'number': number, 'building': False, 'result': 'SUCCESS'}))

    for name in ('restore', 'jenkins_api', 'start_jenkins', 'inner'):
        monkeypatch.setattr(group, name, forbidden)
    monkeypatch.setattr(group, 'require_current_jenkins', lambda: {'id': 'same-private-jenkins', 'running': True})
    monkeypatch.setattr(group, 'original_jenkins_state', status)
    monkeypatch.setattr(group, 'collect_jenkins', collect)
    monkeypatch.setattr(group, 'target', lambda commit: {'manifest': manifest})
    monkeypatch.setattr(group, 'idle', lambda: None)
    monkeypatch.setattr(group, 'finish', lambda folder, engine, before: boundaries.append(before))
    monkeypatch.setattr(group.time, 'sleep', sleeps.append)

    group.execute_engine(tmp_path, 'jenkins', COMMIT, JOB, {}, 'original-baseline', keep_private_jenkins=True)

    assert marker.read_bytes() == original_marker
    assert reads == [(JOB, 28)] * 3 and collections == [(JOB, 28, COMMIT)] * 2
    assert sleeps == [20, 20, 20] and boundaries == ['original-boundary']
    errors = [json.loads(line) for line in (tmp_path / 'jenkins-observation-errors.jsonl').read_text().splitlines()]
    assert [row['phase'] for row in errors] == ['status', 'artifacts']
    assert all(not row['observation_available'] and not row['original_ci_restarted'] for row in errors)
    assert json.loads((tmp_path / 'jenkins-terminal-observed.json').read_text())['number'] == 28


@pytest.mark.parametrize('unavailable_job', sorted(release.JOBS))
def test_full_release_does_not_treat_unavailable_child_as_missing(tmp_path, monkeypatch, unavailable_job):
    builds = {'graphato-release-acceptance': 16, 'graphato-postdeploy-web': 19, JOB: 28}
    marker = tmp_path / 'jenkins-start.json'
    marker.write_text(json.dumps({'builds': builds, 'production_guard_before': 'original-boundary'}))
    original_marker = marker.read_bytes()
    reads, queue_reads, sleeps = [], [], []

    def state(job, number):
        reads.append((job, number))
        if len(reads) <= 3 and job == unavailable_job:
            raise group.JenkinsReadUnavailable('TimeoutExpired')
        return ({'number': number, 'started': True, 'building': False, 'result': 'FAILURE'}
                if job == 'graphato-release-acceptance' else {'number': number, 'started': False})

    def api(path, *args, **kwargs):
        assert len(reads) == 6 and path == '/queue/api/json?tree=items[id]'
        queue_reads.append(path)
        return {'text': '{"items":[]}'}

    def forbidden(*args, **kwargs):
        pytest.fail('No mutation of the original release is authorized by an unavailable read')

    monkeypatch.setattr(group, 'original_jenkins_state', state)
    monkeypatch.setattr(release, 'jenkins_api', api)
    monkeypatch.setattr(release, 'finish', lambda *a, **kw: None)
    monkeypatch.setattr(release.time, 'sleep', sleeps.append)
    monkeypatch.setattr(release, 'inner', forbidden)
    monkeypatch.setattr(release, 'start_jenkins', forbidden)
    monkeypatch.setattr(group, 'restore', forbidden)
    monkeypatch.setattr(group, 'collect_jenkins', forbidden)
    with pytest.raises(RuntimeError, match='parent finished before all child jobs started'):
        release.jenkins(tmp_path, COMMIT, 'original-baseline')
    assert marker.read_bytes() == original_marker and len(reads) == 6 and len(queue_reads) == 1
    assert sleeps == [20]


def test_collection_deadline_does_not_create_a_new_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(group.time, 'monotonic', lambda: 100)
    monkeypatch.setattr(group, 'collect_jenkins', lambda *a: pytest.fail('Deadline has already expired'))
    with pytest.raises(TimeoutError, match='same attempt'):
        group.collect_original_jenkins(tmp_path, JOB, 28, COMMIT, 99)
