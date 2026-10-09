"""Apply and test the independent diagnostic fix after the frozen comparison."""

import json
import time

from finish_current_nas_graphato import phase
from nas_ssh import ROOT


def main():
    capture = ROOT / 'test-results/nas-parity/visual-graphato-ed21c2e6346a-existing-host/report.json'
    deadline = time.monotonic() + 9 * 3600
    while time.monotonic() < deadline:
        if capture.exists():
            assert json.loads(capture.read_text())['passed']
            break
        time.sleep(20)
    else:
        raise TimeoutError('Frozen comparison is not complete; no worker images changed')
    phase('deploy_nas_child_failure_reason.py')
    phase('test_nas_child_failure_reason.py')
    phase('verify_nas_child_failure_reason_ui.cjs', node=True)
    print('Independent worker correction and real negative test complete; manual UI review remains.', flush=True)


if __name__ == '__main__':
    main()
