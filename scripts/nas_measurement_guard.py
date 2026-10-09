"""Keep measurements separate from native Jenkins builds without changing production."""

import json
import re
from datetime import datetime, timezone

from nas_followup_support import production_jobs, wait_production_jobs


def assess(before, after):
    """Detect even a production build that started and finished between samples."""
    def active(state):
        return bool(state.get('active_builds')) or any(row['building'] for row in state['jobs'].values())

    known = before is not None
    unchanged = known and before['jobs'] == after['jobs']
    history = known and before.get('older_concurrent_build_history_verified') is True and after.get('older_concurrent_build_history_verified') is True
    quiet = known and history and not active(before) and not active(after) and unchanged
    return {'production_start_state_recorded': known,
            'production_active_before': active(before) if known else None,
            'production_active_after': active(after),
            'production_job_records_unchanged': unchanged if known else None,
            'older_concurrent_build_history_verified_at_boundaries': history,
            'native_jenkins_quiet_window_verified': quiet,
            'measurement_load_conditions_qualified': quiet,
            'equal_background_load_proven': False,
            'other_nas_workloads_excluded': False,
            'production_paused_or_modified': False}


def begin(folder, phase):
    # Waiting is read-only. Never stop Jenkins or its SCM/timer/user triggers.
    assert re.fullmatch('[a-z0-9-]{1,40}', phase)
    state = wait_production_jobs()
    assert not state.get('active_builds') and not any(row['building'] for row in state['jobs'].values())
    assert state['older_concurrent_build_history_verified'] is True
    name = 'production-measurement-before-' + phase + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'
    path = folder / name
    assert not path.exists()
    path.write_text(json.dumps({'at': datetime.now(timezone.utc).isoformat(), **state}, indent=2) + '\n')
    return name


def finish(folder, phase, before_name):
    assert re.fullmatch('[a-z0-9-]{1,40}', phase)
    path = folder / ('production-measurement-qualification-' + phase + '.json')
    if path.exists():
        # Resuming collection must retain the first observation, including overlap.
        retained = json.loads(path.read_text())
        assert retained['phase'] == phase and retained['before_evidence'] == before_name
        return retained
    before = json.loads((folder / before_name).read_text()) if before_name else None
    after = production_jobs()
    value = {'at': datetime.now(timezone.utc).isoformat(), 'phase': phase,
             'before_evidence': before_name, 'after': after, **assess(before, after)}
    path.write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({'production_measurement_phase': phase,
                      'native_jenkins_quiet_window_verified': value['native_jenkins_quiet_window_verified'],
                      'production_modified': False}), flush=True)
    return value


def qualification_report(folder, phases):
    """Expose missing or overlapping observations in functional test reports."""
    observations = {}
    for phase in phases:
        assert re.fullmatch('[a-z0-9-]{1,40}', phase)
        path = folder / ('production-measurement-qualification-' + phase + '.json')
        observations[phase] = json.loads(path.read_text()) if path.exists() else None
    return {'production_measurement_evidence': observations,
            'measurement_load_conditions_qualified': bool(observations) and all(
                row and row['measurement_load_conditions_qualified'] for row in observations.values()),
            'equal_background_load_proven': False,
            'other_nas_workloads_excluded': False}
