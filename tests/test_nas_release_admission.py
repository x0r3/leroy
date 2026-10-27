"""A measured continuation must leave the complete recovery margin intact."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from nas_release_admission import measured_followup_budget  # noqa: E402


def test_remaining_night_can_fit_observed_full_release_and_engine_overhead():
    result = measured_followup_budget(0, 5400, 6000, 14000)
    assert result['admitted']
    assert result['minimum_stage_seconds'] > 5400 + 300
    assert result['deadline_epoch'] == 14000 and not result['watchdog_deadline_extended']
    assert not result['full_release_success_proven']


def test_stage_duration_alone_cannot_spend_the_recovery_margin():
    result = measured_followup_budget(0, 5400, 6000, 13000)
    assert result['remaining_seconds'] > result['minimum_stage_seconds']
    assert not result['admitted']


@pytest.mark.parametrize('values', [
    (0, 0, 100, 1000), (0, 200, 100, 1000), (0, 100, 1000, 1000),
    (0, float('nan'), 100, 1000), (0, 100, 200, float('inf')),
])
def test_unknown_or_inconsistent_measurement_cannot_admit_another_run(values):
    with pytest.raises(AssertionError):
        measured_followup_budget(*values)
