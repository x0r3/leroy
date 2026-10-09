"""Finish evidence analysis and the distinct prepared-host scenario after the active build."""

import json
import subprocess
import sys
import time

from nas_ssh import ROOT
from stage_nas_production_graphato import COMMIT


def phase(script, *arguments, node=False):
    print('Acceptance phase:', script, *arguments, flush=True)
    prefix = ['node'] if node else [sys.executable, '-X', 'utf8']
    subprocess.run([*prefix, str(ROOT / 'scripts' / script), *arguments], cwd=ROOT, check=True)


def main():
    base = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / COMMIT
    deadline = time.monotonic() + 9 * 3600
    while time.monotonic() < deadline:
        completed = base / 'current-source-comparison.json'
        if completed.is_file():
            break
        time.sleep(10)
    else:
        raise TimeoutError('First comparison not complete; no further target changes applied')
    execution = json.loads(completed.read_text())
    assert execution['jenkins']['builds']['graphato-ci']['result'] == 'SUCCESS'
    assert execution['leroy']['runs']['graphato-ci']['status'] == 'succeeded'
    assert execution['production_jobs_unchanged'] and not execution['application_patches_applied']
    phase('summarize_current_graphato_outcomes.py')
    phase('compare_nas_graphato.py', '--candidate', COMMIT, '--delivery-only')
    phase('analyze_current_nas_graphato.py')
    phase('summarize_nas_acceptance_scope.py')
    run_id = execution['leroy']['runs']['graphato-ci']['id']
    phase('verify_nas_graphato_candidate_ui.cjs', run_id, COMMIT, '--allow-failed', node=True)
    phase('compare_existing_host_nas_graphato.py', 'all')
    phase('analyze_existing_host_nas_graphato.py')
    phase('summarize_nas_acceptance_scope.py')
    scenario = base / 'scenarios/root-private-existing-host'
    root = json.loads((scenario / 'graphato-release-acceptance/pair.json').read_text())['leroy_run']
    phase('verify_nas_graphato_candidate_ui.cjs', root, COMMIT, '--allow-failed', '--release-only', node=True)
    print('Execution analysis and both UI captures complete; manual visual review remains.', flush=True)


if __name__ == '__main__':
    main()
