"""Resume the bounded Rust comparison, observe soak, then test CPU alignment and release."""

import argparse
import json
import re
import subprocess
import sys
import time

from nas_ssh import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--http-attempt', type=int, choices=[1, 2, 3], default=1)
    parser.add_argument('--http-repair-reason')
    args = parser.parse_args()
    assert re.fullmatch('[a-f0-9]{40}', args.commit)
    base = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / args.commit
    rust = base / 'controlled-groups/quality-server-test-round-1/analysis.json'
    deadline = time.monotonic() + 8 * 3600
    while not rust.exists():
        assert time.monotonic() < deadline, 'Original Rust pair incomplete; no dependent workload started'
        time.sleep(20)
    # The retained completed pair is diagnostic evidence, not permission to waive its failures.
    value = json.loads(rust.read_text())
    assert value['commit'] == args.commit and value['same_baseline_snapshot']
    assert all(row['cleanup_complete'] for row in value['engines'].values())

    def phase(script, *arguments):
        print('Frozen diagnosis phase:', script, *arguments, flush=True)
        subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts' / script),
                        '--commit', args.commit, *arguments], cwd=ROOT, check=True)

    diagnostic = ROOT / ('test-results/nas-parity/followup/frozen-soak-http-' + args.commit[:12])
    if args.http_attempt > 1:
        assert args.http_repair_reason
        diagnostic = diagnostic.with_name(diagnostic.name + '-attempt-' + str(args.http_attempt))
    diagnostic_args = ['--attempt', str(args.http_attempt)]
    if args.http_repair_reason:
        diagnostic_args += ['--reason', args.http_repair_reason]
    if not (diagnostic / 'run.json').exists():
        phase('diagnose_frozen_soak_http.py', *diagnostic_args,
              *(['--resume'] if (diagnostic / 'run-id.json').exists() else []))
    else:
        assert json.loads((diagnostic / 'run.json').read_text())['status'] == 'succeeded', 'Inspect retained observation failure'
    for cpus in ('4', '8'):
        phase('compare_frozen_postdeploy_group.py', '--suite', 'web', '--group', 'soak', '--round', '1', '--target-cpus', cpus)
    eight = json.loads((base / 'controlled-groups/web-soak-cpu-eight-round-1/analysis.json').read_text())
    if all(row['requested_passed'] for row in eight['engines'].values()):
        phase('compare_frozen_release_cpu_eight.py')
    else:
        print('Eight-CPU original soak still failed; full release repetition deferred for causal analysis.', flush=True)


if __name__ == '__main__':
    main()
