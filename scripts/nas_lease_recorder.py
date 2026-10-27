"""Follow one exact owned worker before deletion; retain only validated numeric diagnostics."""
import argparse
import json
import os
import re
import select
import subprocess
import time
from pathlib import Path

from observe_nas_release_jobs import safe_transport


def event(line):
    match = re.fullmatch(r'(\d{4}-\d{2}-\d{2}T[0-9:.]+Z) Leroy lease transport: (\{.{1,3000}\})\s*', line)
    if match:
        try:
            value = safe_transport(json.loads(match[2]))
        except (ValueError, TypeError, KeyError):
            return None
        return {'docker_at': match[1], 'transport': value} if value is not None else None
    match = re.fullmatch(r'(\d{4}-\d{2}-\d{2}T[0-9:.]+Z) Leroy lease timing: (\{.{1,1000}\})\s*', line)
    if match:
        try:
            value = json.loads(match[2])
            fields = {'slow_confirmation': {'request_seconds', 'previous_confirmation_age_seconds'},
                      'local_deadline': {'unconfirmed_seconds', 'last_request_seconds', 'loop_gap_seconds'}}
            name = value.pop('event')
            assert name in fields and set(value) == fields[name]
            assert all(v is None or type(v) in (float, int) and 0 <= v < 10**9 for v in value.values())
            return {'docker_at': match[1], 'event': name, **value}
        except (ValueError, TypeError, KeyError, AssertionError):
            return None
    match = re.fullmatch(r'(\d{4}-\d{2}-\d{2}T[0-9:.]+Z) Leroy lease (renewal failed|stopped): '
                         r'(?:Controller lease could not be renewed(?: \(last failure: ([A-Za-z]+|HTTP [0-9]{3})\))?'
                         r'|([A-Za-z]+|HTTP [0-9]{3})(?:; seconds since confirmation: ([0-9.]+))?)\s*', line)
    if match:
        return {'docker_at': match[1], 'event': match[2], 'failure_class': match[3] or match[4],
                'unconfirmed_seconds': float(match[5]) if match[5] else None}
    return None


def run(run_id, folder, deadline):
    assert re.fullmatch('[a-f0-9]{32}', run_id)
    assert deadline > time.time() and deadline <= time.time() + 14400
    from nas_native import validate
    from nas_ssh import ROOT

    validate(ROOT)
    assert folder.resolve().is_relative_to(ROOT / 'test-results/nas-parity/followup')
    path = folder / 'persistent-worker-lease.jsonl'
    outer = json.loads(subprocess.check_output(['docker', 'inspect', 'leroy-nas-parity-docker-1'], timeout=15))[0]
    assert outer['Config']['Labels']['com.docker.compose.project'] == 'leroy-nas-parity'
    prefix = ['docker', 'exec', outer['Id'], 'docker']
    name = 'leroy-' + run_id
    until = min(time.time() + 180, deadline)
    while time.time() < until:
        result = subprocess.run(prefix + ['inspect', name], capture_output=True, timeout=15)
        if result.returncode == 0:
            worker = json.loads(result.stdout)[0]
            assert worker['Config']['Labels']['io.leroy.run'] == run_id
            assert worker['Config']['Labels']['io.leroy.runner'] == 'runner-nas-parity'
            break
        time.sleep(2)
    else:
        raise RuntimeError('Known worker was not observable')
    stream = subprocess.Popen(prefix + ['logs', '--follow', '--timestamps', '--tail', '100', name],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        with path.open('x', encoding='utf-8') as output:
            os.chmod(path, 0o600)
            while time.time() < deadline and output.tell() < 4 * 1024**2:
                if not select.select([stream.stdout], [], [], 3)[0]:
                    if stream.poll() is not None:
                        break
                    continue
                line = stream.stdout.readline(8193)
                if not line:
                    break
                if len(line) > 8192:
                    continue
                value = event(line.decode('utf-8', errors='replace').rstrip())
                if value is not None:
                    output.write(json.dumps({'observed_at_epoch': time.time(), **value}) + '\n')
                    output.flush()
                    os.fsync(output.fileno())
    finally:
        if stream.poll() is None:
            stream.terminate()
            try:
                stream.wait(timeout=5)
            except subprocess.TimeoutExpired:
                stream.kill()
                stream.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--deadline', type=float, required=True)
    args = parser.parse_args()
    run(args.run, args.folder, args.deadline)
