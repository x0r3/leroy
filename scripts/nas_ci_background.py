"""Verify matching CI slots and preserve the private Jenkins during full releases."""

import hashlib
import json
from contextlib import closing

from compare_nas_antares import client
from nas_followup_support import inner, jenkins_api, start_jenkins
from nas_gitea_target import idle
from nas_ssh import ROOT
from nas_test_environment import require_current_jenkins

CAPACITY_PROOF = ROOT / 'test-results/nas-parity/followup/ci-concurrency-20261015/deployment-proof.json'


def capacity_proof():
    raw = CAPACITY_PROOF.read_bytes()
    value = json.loads(raw)
    assert all(value[key] is True for key in (
        'live_private_jenkins_api_verified', 'live_leroy_runner_capacity_verified',
        'images_unchanged', 'controller_process_unchanged', 'native_jenkins_configuration_unchanged'))
    assert all(type(value[key]) is int and value[key] == 2 for key in (
        'native_executors', 'private_jenkins_executors', 'leroy_runner_capacity'))
    assert value['production_cutover'] is False
    return hashlib.sha256(raw).hexdigest()


def validate_live_capacity(computers, runners):
    assert len(computers) == 1, 'Unexpected private Jenkins agents'
    assert type(computers[0]['numExecutors']) is int and computers[0]['numExecutors'] == 2
    assert computers[0]['offline'] is False
    records = [row for row in runners if row['id'] == 'runner-nas-parity']
    assert len(records) == 1 and records[0]['online'] is True
    assert type(records[0]['capacity']) is int and records[0]['capacity'] == 2


def snapshot():
    proof = capacity_proof()
    expected = require_current_jenkins()
    actual, = json.loads(inner('inspect', 'jenkins-parity'))
    assert expected['running'] and actual['State']['Running']
    assert actual['Id'] == expected['id'] and actual['Image'] == expected['image']
    computers = json.loads(jenkins_api('/computer/api/json?tree=computer[displayName,numExecutors,offline]')['text'])['computer']
    with closing(client()) as api:
        response = api.get('/api/runners')
        response.raise_for_status()
        runners = response.json()
    validate_live_capacity(computers, runners)
    return {'capacity_alignment_proof_sha256': proof,
            'private_jenkins_process': {'id': actual['Id'], 'image': actual['Image'],
                                      'pid': actual['State']['Pid'], 'started_at': actual['State']['StartedAt'],
                                      'restart_count': actual['RestartCount']},
            'native_executors': 2, 'private_jenkins_executors': 2, 'leroy_runner_capacity': 2,
            'private_jenkins_running': True, 'production_modified': False}


def record(folder, engine, boundary):
    assert engine in {'leroy', 'jenkins'} and boundary in {'before', 'after'}
    value = snapshot()
    before = folder / (engine + '-ci-background-before.json')
    if boundary == 'after':
        original = json.loads(before.read_text())
        assert value == original, 'CI capacity or private Jenkins process changed during this release'
    path = folder / (engine + '-ci-background-' + boundary + '.json')
    if path.exists():
        assert json.loads(path.read_text()) == value, 'Retain the first CI background observation'
    else:
        path.write_text(json.dumps(value, indent=2) + '\n')
    return value


def prepare(folder, engine):
    start_jenkins()
    if not (folder / (engine + '-start.json')).exists():
        idle()
    return record(folder, engine, 'before')


def paired_proof(folder):
    records = {engine: {boundary: json.loads((folder / (engine + '-ci-background-' + boundary + '.json')).read_text())
                        for boundary in ('before', 'after')} for engine in ('leroy', 'jenkins')}
    for engine, value in records.items():
        assert value['before'] == value['after'], 'Private Jenkins changed during ' + engine
    first, second = (records[engine]['before'] for engine in ('leroy', 'jenkins'))
    for key in ('capacity_alignment_proof_sha256', 'native_executors', 'private_jenkins_executors',
                'leroy_runner_capacity', 'private_jenkins_running'):
        assert first[key] == second[key]
    return {'both_ci_controllers_present_both_measurements': True,
            'private_jenkins_process_unchanged_during_each_release': True,
            'matching_production_ci_slots_verified': True, 'records': records,
            'equal_background_load_proven': False}
