"""Equal failed groups must not hide different failed original test cases."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import compare_nas_original_test_outcomes as outcomes  # noqa: E402


def test_two_failed_groups_still_expose_startup_outcome_difference():
    jenkins = {'focus': 'failed', 'startup': 'failed', 'other': 'passed'}
    leroy = {'focus': 'failed', 'startup': 'passed', 'other': 'passed'}
    assert outcomes.outcome_difference(jenkins, leroy) == [
        {'identity': 'startup', 'jenkins': 'failed', 'leroy': 'passed'}]


def test_missing_original_case_is_not_counted_as_success():
    assert outcomes.outcome_difference({'case': 'passed'}, {}) == [
        {'identity': 'case', 'jenkins': 'passed', 'leroy': 'missing'}]


def test_duplicate_failure_details_after_summary_do_not_duplicate_case_identity():
    data = ('✔ utility (1ms)\nℹ tests 1\nℹ pass 1\nℹ duration_ms 1\n'
            '✔ startup (2ms)\n✖ focus (3ms)\nℹ tests 2\nℹ pass 1\nℹ fail 1\n'
            'ℹ cancelled 0\nℹ skipped 0\nℹ todo 0\nℹ duration_ms 5\n'
            '✖ focus (3ms)\nError: expected focused\n').encode()
    assert outcomes.component_outcomes(data) == {'startup': 'passed', 'focus': 'failed'}


def test_incomplete_component_log_cannot_claim_parity():
    with pytest.raises(AssertionError):
        outcomes.component_outcomes('✔ startup (2ms)\n'.encode())


def test_duplicate_rust_names_retain_event_multiplicity():
    data = b'{"type":"test","event":"ok","name":"same"}\n{"type":"test","event":"ok","name":"same"}\n{"type":"test","event":"ignored","name":"same"}\n'
    value = outcomes.rust_events(data)
    assert value['same', 'ok'] == 2 and value['same', 'ignored'] == 1
