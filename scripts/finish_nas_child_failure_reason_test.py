"""Finish validation of the same red runs after repairing an exit-boundary assumption."""

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
from test_nas_child_failure_reason import verify_command_failure


def main():
    folder = ROOT / 'test-results/nas-parity/followup/child-failure-reason-nas'
    assert (folder / 'validation-repair.json').exists() and not (folder / 'report.json').exists()
    idle()
    deployment = json.loads((folder.parent / 'child-failure-reason-deployment.json').read_text())
    run_id = json.loads((folder / 'run-id.json').read_text())['id']
    expected_image = deployment['images']['leroy-job:nas-parity']['after']
    with closing(client()) as api:
        response = api.get('/api/runs/' + run_id)
        response.raise_for_status()
        run = response.json()
        assert run['pipeline_id'] == 'leroy-nas-child-reason-parent'
        assert run['status'] == 'failed' and run['reason'] == 'acceptance: Child job did not succeed'
        assert run['steps'][0]['reason'] == 'Child job did not succeed' and len(run['children']) == 1
        response = api.get('/api/runs/' + run['children'][0]['id'])
        response.raise_for_status()
        child = response.json()
        assert child['parent_id'] == run_id and child['status'] == 'failed'
        assert child['pipeline_id'] == 'leroy-nas-diagnostics'
        assert run['image_digest'] == child['image_digest'] == expected_image
        assert run['id'] == json.loads((folder / 'parent-run.json').read_text())['id']
        assert child['id'] == json.loads((folder / 'child-run.json').read_text())['id']
        verify_command_failure(api, child, folder)
        for value, name in ((run, 'parent'), (child, 'child')):
            collect_artifacts(api, value, folder / name)
        definitions = api.get('/api/pipelines').json()
        assert not any(p['enabled'] for p in definitions)
        restored = next(p['spec'] for p in definitions if p['id'] == 'leroy-nas-diagnostics')
        assert restored == json.loads((folder / 'previous-diagnostic-definition.json').read_text())
    deadline = time.monotonic() + 60
    while inner('ps', '-a', '--filter', 'label=io.leroy.runner=runner-nas-parity', '-q').strip():
        assert time.monotonic() < deadline, 'Owned jobs still await cleanup'
        time.sleep(3)
    before = json.loads((folder / 'production-jobs-before.json').read_text())
    after = production_jobs()
    (folder / 'production-jobs-after.json').write_text(json.dumps(after, indent=2) + '\n')
    unchanged = before['jobs'] == after['jobs']
    if not unchanged:
        activity = collect_activity(before['jobs'], after['jobs'])
        (folder / 'production-activity-audit.json').write_text(json.dumps(activity, indent=2) + '\n')
        assert activity['all_changed_builds_have_recognized_trigger_causes']
        assert not activity['production_builds_triggered_by_this_task']
    report = {'at': datetime.now(timezone.utc).isoformat(), 'passed': True,
              'expected_pipeline_failure': True, 'parent_run': run_id, 'child_run': child['id'],
              'parent_reason': run['reason'], 'both_runs_remain_failed': True,
              'underlying_command_exit_status': 17, 'action_launcher_exit_code': 1,
              'updated_image_used': expected_image, 'job_containers_removed': True,
              'previous_diagnostic_definition_restored': True, 'production_jobs_unchanged': unchanged,
              'independent_production_activity_audited': not unchanged, 'production_modified': False,
              'application_patches_applied': False, 'resumed_validation_same_runs': True,
              'validation_repair_evidence': (folder / 'validation-repair.json').relative_to(ROOT).as_posix()}
    (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
