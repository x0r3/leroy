"""Prepare one explicit retry after preserving the cancelled run and changing control residency."""

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from compare_existing_host_nas_graphato import FOLDER, JOBS
from nas_gitea_target import idle
from nas_ssh import ROOT


def extended(path):
    return chr(92) * 2 + '?' + chr(92) + str(path.resolve())


def main():
    idle()
    assert not (FOLDER / 'explicit-leroy-retry.json').exists()
    archive = FOLDER / 'attempts/leroy-95-cancelled'
    proof = json.loads((archive / 'interruption.json').read_text())
    assert proof['status'] == 'cancelled' and not proof['comparison_passed']
    for name in proof['preserved_files']:
        source, backup = FOLDER / name, Path(extended(archive / name))
        assert hashlib.sha256(source.read_bytes()).digest() == hashlib.sha256(backup.read_bytes()).digest()
    trial = json.loads((ROOT / 'test-results/nas-parity/followup/control-plane-residency-workload/report.json').read_text())
    assert trial['passed'] and trial['duration_at_least_240_seconds']
    deployment = json.loads((ROOT / 'test-results/nas-parity/followup/control-plane-residency-deployment.json').read_text())
    assert deployment['worker_images_unchanged'] and deployment['lease_seconds_unchanged'] == 90
    assert deployment['worker_confirmation_seconds_unchanged'] == 45
    # Move only the previous Leroy outputs. The immutable hash-checked archive
    # remains available, and Jenkins evidence stays in its original location.
    retired = FOLDER / 'retired-leroy-95'
    assert not retired.exists() and retired.resolve().is_relative_to(ROOT.resolve())
    retired.mkdir()
    selected = [FOLDER / name for name in ('leroy-snapshot-restore.json', 'leroy-target-before.json',
                'leroy-target-after.json', 'leroy-progress.json', 'executions.json', 'production-jobs-after.json')]
    for job in JOBS:
        folder = FOLDER / job
        selected.extend(path for path in folder.iterdir() if path.name.startswith('leroy-'))
        pair_path = folder / 'pair.json'
        pair = json.loads(pair_path.read_text())
        pair.pop('leroy_run', None)
        pair.pop('leroy_status', None)
        pair_path.write_text(json.dumps(pair, indent=2) + '\n')
    for path in selected:
        if not path.exists():
            continue
        destination = retired / path.relative_to(FOLDER)
        assert path.resolve().is_relative_to(FOLDER.resolve()) and destination.resolve().is_relative_to(retired.resolve())
        Path(extended(destination.parent)).mkdir(parents=True, exist_ok=True)
        shutil.move(extended(path), extended(destination))
    record = {'at': datetime.now(timezone.utc).isoformat(), 'previous_attempt': archive.relative_to(ROOT).as_posix(),
              'previous_status': 'cancelled', 'reason': 'Control plane residency changed after lease confirmation timeouts',
              'original_application_and_snapshot_unchanged': True, 'worker_images_unchanged': True,
              'lease_budgets_unchanged': True, 'application_patches_applied': False, 'root_cause_proven': False}
    (FOLDER / 'explicit-leroy-retry.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
