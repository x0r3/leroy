"""A green group receipt cannot hide incomplete or unrelated original test evidence."""

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def quality_evidence(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    parser = importlib.import_module('analyze_existing_host_nas_graphato')
    identity = {'commit': 'a' * 40, 'runtimeImageId': 'sha256:' + 'b' * 64,
                'sourceSha256': 'c' * 64, 'buildTimestamp': '20261005220000', 'suite': 'quality'}
    events = [{'type': 'suite', 'event': 'started', 'test_count': 2},
              {'type': 'test', 'event': 'ok', 'name': 'original::test'},
              {'type': 'test', 'event': 'ignored', 'name': 'original::disabled'}]
    files = {'rust-test-times.json': json.dumps({**identity, 'complete': True, 'expectedTests': 1,
                                              'measuredTests': 1}).encode(),
             'server-test.log': ('\n'.join(json.dumps(row) for row in events)).encode(),
             'frontend-and-deployment.log': b'Ran 146 tests in 2.422s\n\nFAILED (errors=1)\n'}
    receipt = {'identity': identity, 'checks': {'server-test': {'passed': True}}}
    return parser, files, receipt


def test_original_names_and_ignored_tests_are_counted_without_patch_requirements(quality_evidence):
    parser, files, receipt = quality_evidence
    result = parser.quality_tests(files, receipt)
    assert result['rust']['expected'] == 2 and result['rust']['ok'] == result['rust']['ignored'] == 1
    assert result['deployment_python'] == {'tests': 146, 'result': 'FAILED (errors=1)'}


def test_missing_terminal_event_cannot_certify_complete_group(quality_evidence):
    parser, files, receipt = quality_evidence
    files['server-test.log'] = files['server-test.log'].rsplit(b'\n', 1)[0]
    with pytest.raises(AssertionError):
        parser.quality_tests(files, receipt)


def test_other_commit_cannot_supply_test_counts(quality_evidence):
    parser, files, receipt = quality_evidence
    timing = json.loads(files['rust-test-times.json'])
    timing['commit'] = 'd' * 40
    files['rust-test-times.json'] = json.dumps(timing).encode()
    with pytest.raises(AssertionError):
        parser.quality_tests(files, receipt)


def test_test_failure_cannot_be_hidden_by_successful_group_receipt(quality_evidence):
    parser, files, receipt = quality_evidence
    files['server-test.log'] = files['server-test.log'].replace(b'"event": "ignored"', b'"event": "failed"')
    with pytest.raises(AssertionError):
        parser.quality_tests(files, receipt)


def test_complete_failed_rust_run_preserves_the_failure_instead_of_rejecting_its_evidence(quality_evidence):
    parser, files, receipt = quality_evidence
    files['server-test.log'] = files['server-test.log'].replace(b'"event": "ignored"', b'"event": "failed"')
    timings = json.loads(files['rust-test-times.json'])
    timings.update(expectedTests=2, measuredTests=2)
    files['rust-test-times.json'] = json.dumps(timings).encode()
    receipt['checks']['server-test']['passed'] = False
    result = parser.quality_tests(files, receipt)['rust']
    assert result['expected'] == 2 and result['ok'] == result['failed'] == 1 and result['ignored'] == 0
    assert result['failed_tests'] == ['original::disabled']


@pytest.mark.parametrize('failed', [False, True])
def test_multiple_python_suites_preserve_all_counts_and_failures(quality_evidence, failed):
    parser, files, receipt = quality_evidence
    summaries = [(146, 'OK'), (17, 'OK'), (13, 'OK'), (7, 'OK'), (4, 'OK'),
                 (8, 'FAILED (errors=1)' if failed else 'OK')]
    files['frontend-and-deployment.log'] = ''.join(
        f'Ran {count} tests in 0.123s\n\n{result}\n' for count, result in summaries).encode()
    result = parser.quality_tests(files, receipt)['deployment_python']
    assert result['tests'] == 195
    assert result['result'] == ('FAILED (errors=1)' if failed else 'OK')
    assert result['summaries'] == [{'tests': count, 'result': value} for count, value in summaries]


def test_truncated_later_python_summary_cannot_disappear_from_counts(quality_evidence):
    parser, files, receipt = quality_evidence
    files['frontend-and-deployment.log'] += b'Ran 8 tests in 0.123s\n\n'
    with pytest.raises(AssertionError, match='truncated Python'):
        parser.quality_tests(files, receipt)
