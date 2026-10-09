"""Retain the interrupted comparison, then explicitly repeat its unchanged-source Leroy CI."""

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from nas_followup_support import production_jobs
from nas_gitea_target import idle
from nas_ssh import ROOT
from prepare_nas_vm import guest
from stage_nas_production_graphato import COMMIT


def read(path):
    return json.loads(path.read_text())


def phase(name, *args, failed_result_allowed=False):
    print('Retained-attempt recovery:', name, *args, flush=True)
    result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts' / name), *args], cwd=ROOT)
    if result.returncode and not failed_result_allowed:
        raise RuntimeError('Inspect the recorded recovery result: ' + name)


def main():
    base = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / COMMIT
    pair_path = base / 'graphato-ci/pair.json'
    pair = read(pair_path)
    execution = read(base / 'current-source-comparison.json')
    old = read(base / 'graphato-ci/leroy-run.json')
    assert old['id'] == pair['leroy_run'] and old['status'] == 'interrupted' and old['number'] == 90
    assert old['reason'] == 'Runner lease expired; external effects require reconciliation'
    assert not execution['application_patches_applied'] and execution['production_jobs_unchanged']
    deployment = read(base / 'control-residency-deployment.json')
    assert deployment['graphato_job_swap_limit_bytes'] == 0 and deployment['lease_seconds_unchanged'] == 90
    assert not deployment['application_patches_applied'] and not deployment['production_modified']
    idle()
    guest('sudo test -f /var/lib/leroy-vm/ready && sudo test ! -e /opt/graphato/current', timeout=20)
    archive = base / 'attempts/leroy-90-interrupted'
    archive.mkdir(parents=True, exist_ok=False)
    paths = [base / name for name in ['current-source-comparison.json', 'current-source-outcomes.json',
             'leroy-run-watch.json', 'leroy-run-progress.jsonl']]
    paths += [path for path in (base / 'graphato-ci').glob('leroy-*')]
    (archive / 'graphato-ci').mkdir()
    (archive / 'graphato-ci/pair.json').write_bytes(pair_path.read_bytes())
    for path in paths:
        if not path.exists():
            continue
        destination = archive / path.relative_to(base)
        assert path.resolve().is_relative_to(base.resolve()) and destination.resolve().is_relative_to(archive.resolve())
        assert not destination.exists()
        shutil.move(str(path.resolve()), str(destination.resolve()))
    recovery = {'at': datetime.now(timezone.utc).isoformat(), 'previous_run': old['id'], 'commit': COMMIT,
                'reason': 'Controller and database stayed healthy while the job lost its lease. Add bounded lease diagnostics and prevent swap for the small job-control container; retain original builder budgets.',
                'deployment_evidence': (base / 'control-residency-deployment.json').relative_to(ROOT).as_posix(),
                'same_prepared_fresh_application_target': True, 'application_patches_applied': False,
                'production_modified': False, 'lease_seconds_unchanged': 90}
    (archive / 'recovery.json').write_text(json.dumps(recovery, indent=2) + '\n')
    for key in ['leroy_run', 'leroy_status', 'resource_policy_evidence']:
        pair.pop(key, None)
    pair['retained_leroy_attempts'] = [{'run': old['id'], 'number': old['number'], 'status': old['status'],
                                    'evidence': archive.relative_to(ROOT).as_posix()}]
    pair_path.write_text(json.dumps(pair, indent=2) + '\n')
    phase('compare_nas_job.py', 'graphato-ci', 'start-leroy', '--candidate', COMMIT)
    phase('watch_nas_graphato_leroy.py', '--candidate', COMMIT, failed_result_allowed=True)
    observed = read(base / 'leroy-run-watch.json')
    if observed['runs']['graphato-ci']['status'] == 'succeeded':
        phase('nas_graphato_release_state.py', 'leroy', '--candidate', COMMIT)
    after = production_jobs()
    before = read(base / 'production-jobs-before.json')
    (base / 'production-jobs-after.json').write_text(json.dumps(after, indent=2) + '\n')
    execution.update(at=datetime.now(timezone.utc).isoformat(), leroy=observed,
                     production_jobs_unchanged=before['jobs'] == after['jobs'],
                     retained_leroy_attempts=pair['retained_leroy_attempts'],
                     workload_success_both=all(r.get('result') == 'SUCCESS' for r in execution['jenkins']['builds'].values()) and observed['all_successful'])
    (base / 'current-source-comparison.json').write_text(json.dumps(execution, indent=2) + '\n')
    print(json.dumps({'runs': observed['runs'], 'workload_success_both': execution['workload_success_both']}), flush=True)


if __name__ == '__main__':
    main()
