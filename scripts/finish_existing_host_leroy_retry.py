"""Wait for the real control-plane probe, then run one explicitly prepared comparison retry."""

import json
import time

from compare_existing_host_nas_graphato import FOLDER
from finish_current_nas_graphato import phase
from nas_ssh import ROOT
from stage_nas_production_graphato import COMMIT


def main():
    report = ROOT / 'test-results/nas-parity/followup/control-plane-residency-workload/report.json'
    deadline = time.monotonic() + 900
    while not report.exists() and time.monotonic() < deadline:
        time.sleep(5)
    assert report.exists() and json.loads(report.read_text())['passed']
    phase('prepare_existing_host_leroy_retry.py')
    phase('compare_existing_host_nas_graphato.py', 'retry-leroy')
    phase('audit_nas_production_activity.py')
    phase('analyze_existing_host_nas_graphato.py')
    phase('summarize_nas_acceptance_scope.py')
    run_id = json.loads((FOLDER / 'graphato-release-acceptance/pair.json').read_text())['leroy_run']
    phase('verify_nas_graphato_candidate_ui.cjs', run_id, COMMIT, '--allow-failed', '--release-only', node=True)
    print('Explicit prepared-host retry complete; manual UI review remains.', flush=True)


if __name__ == '__main__':
    main()
