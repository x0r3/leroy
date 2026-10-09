"""A generic deployment error or an unrelated probe cannot certify failure parity."""

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    parser = importlib.import_module('analyze_current_nas_graphato')
    monkeypatch.setattr(parser, 'ROOT', tmp_path)
    folder = tmp_path / 'graphato-postdeploy-web'
    folder.mkdir()
    (folder / 'jenkins-5-console.log').write_text('CI deployment failed (ValueError); inspect the deployment stage.')
    (folder / 'leroy-web.log').write_text('CI deployment failed (ValueError); inspect the deployment stage.')
    target = {'postdeploy_control_directory': {'exists': True, 'is_directory': True,
              'is_symlink': False, 'mode': '0o755', 'uid': 0},
              'manifest': {'commit': 'a' * 40, 'files': {'deployments/linux/host/postdeploy.py': 'b' * 64}}}
    probe = {'captured_target_precondition': target['postdeploy_control_directory'], 'commit': 'a' * 40,
             'application_source_sha256': 'b' * 64, 'original_marker_validation_error': 'Run markers require root-private directories',
             'captured_mode_reproduced': True, 'temporary_fixture_removed': True,
             'actual_application_directory_modified': False}
    return parser, folder, target, probe


def test_generic_error_without_probe_stays_unclassified(evidence):
    parser, folder, target, _ = evidence
    result = parser.suite_receipt(folder, 'jenkins', {'jenkins': {'number': 5}}, 'web', target)
    assert result['startup_failure'] is None and result['checks_executed'] is None
    assert result['complete_suite_passed'] is False


def test_reconstruction_with_verified_source_classifies_zero_executed_checks(evidence):
    parser, folder, target, probe = evidence
    (folder.parent / 'marker-precondition-reproduction.json').write_text(json.dumps(probe))
    result = parser.suite_receipt(folder, 'jenkins', {'jenkins': {'number': 5}}, 'web', target)
    assert result['startup_failure'] == 'Run markers require root-private directories'
    assert result['checks_executed'] == 0 and result['complete_suite_passed'] is False
    assert result['diagnostic_scope'] == 'captured metadata plus unchanged-source temporary reproduction'


@pytest.mark.parametrize('field,value', [('application_source_sha256', 'c' * 64), ('commit', 'd' * 40)])
def test_probe_from_other_source_cannot_classify_failure(evidence, field, value):
    parser, folder, target, probe = evidence
    probe[field] = value
    (folder.parent / 'marker-precondition-reproduction.json').write_text(json.dumps(probe))
    result = parser.suite_receipt(folder, 'jenkins', {'jenkins': {'number': 5}}, 'web', target)
    assert result['startup_failure'] is None and result['failure_analysis_complete'] is False


def test_jenkins_reconstruction_cannot_substitute_for_leroy_probe(evidence):
    parser, folder, target, probe = evidence
    (folder.parent / 'marker-precondition-reproduction.json').write_text(json.dumps(probe))
    result = parser.suite_receipt(folder, 'leroy', {'jenkins': {'number': 5}}, 'web', target)
    assert result['startup_failure'] is None and result['failure_analysis_complete'] is False
