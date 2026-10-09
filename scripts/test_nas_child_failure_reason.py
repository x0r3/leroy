"""Exercise a real failed child on the NAS; preserve the deliberately red runs."""

import json
import time
from contextlib import closing
from datetime import datetime, timezone

from audit_nas_production_activity import collect_activity
from compare_nas_antares import client
from compare_nas_job import collect_artifacts
from nas_followup_support import inner, production_jobs
from nas_gitea_target import idle
from nas_ssh import ROOT

from leroy.schema import Pipeline, Step


def verify_command_failure(api, child_run, folder):
    """Verify the launcher failure and its underlying command separately."""
    step = child_run['steps'][0]
    assert step['id'] == 'probe' and step['exit_code'] == 1
    assert 0 < step['log_bytes'] < 65536
    response = api.get('/api/runs/' + child_run['id'] + '/logs/probe', params={'offset': 0})
    response.raise_for_status()
    log = response.json()
    assert log['next_offset'] == step['log_bytes']
    assert 'CalledProcessError' in log['text'] and 'returned non-zero exit status 17' in log['text']
    (folder / 'child-probe.log').write_text(log['text'])


def main():
    base = ROOT / 'test-results/nas-parity/followup'
    folder = base / 'child-failure-reason-nas'
    assert not folder.exists(), 'Retain each negative test; no implicit repetition'
    deployment = json.loads((base / 'child-failure-reason-deployment.json').read_text())
    idle()
    before = production_jobs()
    folder.mkdir()
    (folder / 'production-jobs-before.json').write_text(json.dumps(before, indent=2) + '\n')
    parent_id = 'leroy-nas-child-reason-parent'
    child_id = 'leroy-nas-diagnostics'
    with closing(client()) as api:
        definitions = api.get('/api/pipelines').json()
        assert not any(p['enabled'] for p in definitions)
        assert not any(p['id'] == parent_id for p in definitions)
        saved = next(p['spec'] for p in definitions if p['id'] == child_id)
        assert saved['source']['kind'] == 'diagnostic'
        (folder / 'previous-diagnostic-definition.json').write_text(json.dumps(saved, indent=2) + '\n')
        child = Pipeline(id=child_id, name='NAS-Negativtest: Kindlauf endet mit Exitcode 17', group='Abnahme',
                         enabled=False, profile='graphato', timeout=120,
                         source={'kind': 'diagnostic', 'scenario': 'child-failure-reason', 'expected_failure': True},
                         steps=[Step(id='probe', name='Expected failure', timeout=30,
                                     command=['python', '-c', 'raise SystemExit(17)'])])
        parent = Pipeline(id=parent_id, name='NAS-Negativtest: Kindlauf-Grund', group='Abnahme',
                          enabled=False, profile='graphato', timeout=180,
                          source={'kind': 'diagnostic', 'scenario': 'child-failure-reason', 'expected_failure': True},
                          steps=[Step(id='acceptance', name='Expected failed child', action='child', timeout=120,
                                      options={'pipeline': child_id, 'wait': True})])
        for spec in (child, parent):
            (folder / (spec.id + '.json')).write_text(spec.model_dump_json(indent=2))
            api.put('/api/pipelines/' + spec.id, json=spec.model_dump()).raise_for_status()
        response = api.post('/api/pipelines/' + parent_id + '/runs', json={})
        response.raise_for_status()
        run_id = response.json()['id']
        (folder / 'run-id.json').write_text(json.dumps({'id': run_id}) + '\n')
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            response = api.get('/api/runs/' + run_id)
            response.raise_for_status()
            run = response.json()
            if run['status'] not in ('running', 'waiting', 'queued'):
                break
            time.sleep(3)
        else:
            raise TimeoutError('Negative test still active; no cancellation or repeat')
        (folder / 'parent-run.json').write_text(json.dumps(run, indent=2) + '\n')
        assert run['status'] == 'failed' and run['reason'] == 'acceptance: Child job did not succeed'
        assert len(run['children']) == 1 and run['steps'][0]['reason'] == 'Child job did not succeed'
        response = api.get('/api/runs/' + run['children'][0]['id'])
        response.raise_for_status()
        child_run = response.json()
        (folder / 'child-run.json').write_text(json.dumps(child_run, indent=2) + '\n')
        assert child_run['parent_id'] == run_id and child_run['status'] == 'failed'
        verify_command_failure(api, child_run, folder)
        expected_image = deployment['images']['leroy-job:nas-parity']['after']
        assert run['image_digest'] == child_run['image_digest'] == expected_image
        collect_artifacts(api, run, folder / 'parent')
        collect_artifacts(api, child_run, folder / 'child')
        api.put('/api/pipelines/' + child_id, json=saved).raise_for_status()
        assert not any(p['enabled'] for p in api.get('/api/pipelines').json())
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        remaining = inner('ps', '-a', '--filter', 'label=io.leroy.runner=runner-nas-parity', '-q').strip()
        if not remaining:
            break
        time.sleep(3)
    else:
        raise TimeoutError('Owned jobs have not finished cleanup')
    after = production_jobs()
    (folder / 'production-jobs-after.json').write_text(json.dumps(after, indent=2) + '\n')
    unchanged = before['jobs'] == after['jobs']
    if not unchanged:
        activity = collect_activity(before['jobs'], after['jobs'])
        (folder / 'production-activity-audit.json').write_text(json.dumps(activity, indent=2) + '\n')
        assert activity['all_changed_builds_have_recognized_trigger_causes']
        assert not activity['production_builds_triggered_by_this_task']
    report = {'at': datetime.now(timezone.utc).isoformat(), 'passed': True, 'expected_pipeline_failure': True,
              'parent_run': run_id, 'child_run': child_run['id'], 'parent_reason': run['reason'],
              'underlying_command_exit_status': 17, 'action_launcher_exit_code': 1,
              'both_runs_remain_failed': True, 'updated_image_used': expected_image, 'job_containers_removed': True,
              'previous_diagnostic_definition_restored': True, 'production_jobs_unchanged': unchanged,
              'independent_production_activity_audited': not unchanged,
              'production_modified': False, 'application_patches_applied': False}
    (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
