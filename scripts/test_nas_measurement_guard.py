"""Check that production overlap cannot be mistaken for a controlled measurement."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nas_measurement_guard import assess, finish, qualification_report


def snapshot(number=26, *, building=False, older_active=False):
    return {'jobs': {'graphato-ci': {'number': number, 'building': building,
                                    'result': None if building else 'SUCCESS'}},
            'active_builds': [{'job': 'graphato-ci', 'number': number - 1}] if older_active else [],
            'older_concurrent_build_history_verified': True}


class MeasurementQualificationTests(unittest.TestCase):
    def test_build_started_and_finished_between_idle_samples_invalidates_comparison(self):
        result = assess(snapshot(26), snapshot(27))
        self.assertFalse(result['measurement_load_conditions_qualified'])
        self.assertFalse(result['production_active_before'])
        self.assertFalse(result['production_active_after'])

    def test_older_concurrent_build_blocks_quiet_despite_completed_latest_record(self):
        result = assess(snapshot(27, older_active=True), snapshot(27))
        self.assertTrue(result['production_active_before'])
        self.assertFalse(result['native_jenkins_quiet_window_verified'])

    def test_historical_run_without_start_guard_never_gets_retroactive_quiet_claim(self):
        result = assess(None, snapshot())
        self.assertIsNone(result['production_active_before'])
        self.assertFalse(result['measurement_load_conditions_qualified'])

    def test_recorded_quiet_window_does_not_claim_equal_host_load(self):
        result = assess(snapshot(), snapshot())
        self.assertTrue(result['native_jenkins_quiet_window_verified'])
        self.assertFalse(result['equal_background_load_proven'])
        self.assertFalse(result['other_nas_workloads_excluded'])
        self.assertFalse(result['production_paused_or_modified'])

    def test_unverified_concurrent_history_cannot_qualify_an_idle_latest_build(self):
        before = snapshot()
        before.pop('older_concurrent_build_history_verified')
        self.assertFalse(assess(before, snapshot())['measurement_load_conditions_qualified'])

    def test_resume_retains_first_overlap_observation_even_when_production_is_idle(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            before_name = 'production-before.json'
            (folder / before_name).write_text(json.dumps(snapshot()))
            with patch('nas_measurement_guard.production_jobs', return_value=snapshot(27, building=True)):
                first = finish(folder, 'leroy', before_name)
            path = folder / 'production-measurement-qualification-leroy.json'
            original_bytes = path.read_bytes()
            with patch('nas_measurement_guard.production_jobs') as query:
                self.assertEqual(finish(folder, 'leroy', before_name), first)
                query.assert_not_called()
            self.assertEqual(path.read_bytes(), original_bytes)
            self.assertFalse(first['measurement_load_conditions_qualified'])

    def test_pair_report_requires_observations_for_both_engines(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            quiet = {'measurement_load_conditions_qualified': True}
            (folder / 'production-measurement-qualification-leroy.json').write_text(json.dumps(quiet))
            report = qualification_report(folder, ('leroy', 'jenkins'))
            self.assertFalse(report['measurement_load_conditions_qualified'])
            self.assertIsNone(report['production_measurement_evidence']['jenkins'])
            (folder / 'production-measurement-qualification-jenkins.json').write_text(
                json.dumps({'measurement_load_conditions_qualified': False}))
            self.assertFalse(qualification_report(folder, ('leroy', 'jenkins'))['measurement_load_conditions_qualified'])


if __name__ == '__main__':
    unittest.main()
