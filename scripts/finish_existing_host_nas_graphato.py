"""Finish the explicitly resumed prepared-host comparison after Jenkins completes."""

import json
import time

from finish_current_nas_graphato import phase
from nas_followup_support import inner
from nas_ssh import ROOT
from stage_nas_production_graphato import COMMIT
from watch_nas_graphato_via_leroy import JENKINS_ID


def main():
    base = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / COMMIT
    scenario = base / 'scenarios/root-private-existing-host'
    assert (scenario / 'preflight-banner-timeout.json').is_file()
    assert not (scenario / 'leroy-snapshot-restore.json').exists(), 'No implicit rerun'
    deadline = time.monotonic() + 9 * 3600
    while time.monotonic() < deadline:
        if (scenario / 'jenkins-target-after.json').exists():
            assert inner('inspect', 'jenkins-parity', '--format', '{{.Id}}').strip() == JENKINS_ID
            if inner('inspect', 'jenkins-parity', '--format', '{{.State.Running}}').strip() == 'false':
                break
        time.sleep(20)
    else:
        raise TimeoutError('Jenkins comparison is not complete; no Leroy jobs started')
    phase('compare_existing_host_nas_graphato.py', 'leroy')
    phase('analyze_existing_host_nas_graphato.py')
    phase('summarize_nas_acceptance_scope.py')
    run_id = json.loads((scenario / 'graphato-release-acceptance/pair.json').read_text())['leroy_run']
    phase('verify_nas_graphato_candidate_ui.cjs', run_id, COMMIT, '--allow-failed', '--release-only', node=True)
    print('Prepared-host comparison completed; manual visual review remains.', flush=True)


if __name__ == '__main__':
    main()
