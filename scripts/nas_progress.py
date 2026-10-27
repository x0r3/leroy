"""Publish whole observation snapshots and retain known run IDs through read gaps."""
import json
import os
import tempfile
import time
from pathlib import Path


def read_json(path):
    data = Path(path).read_bytes()
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        # Retain source-bound historical Windows approvals byte for byte.
        text = data.decode('cp1252')
    return json.loads(text)


def publish(path, value):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', suffix='.pending', dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(value, indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        # A Windows reader can briefly deny replacement. Only publication of the
        # same local metadata is retried; no CI or remote operation occurs here.
        for attempt in range(10):
            try:
                os.replace(temporary, path)
                if os.name == 'posix':
                    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(directory)
                    finally:
                        os.close(directory)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.01)
    finally:
        temporary.unlink(missing_ok=True)


def run_ids(case):
    identities = set()
    marker = case / 'leroy-start.json'
    if marker.is_file():
        identities.add(json.loads(marker.read_text(encoding='utf-8'))['id'])
    progress = case / 'leroy-progress.json'
    if progress.is_file():
        try:
            value = json.loads(progress.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            # A retained legacy writer can still expose an incomplete snapshot.
            # Register the authoritative start ID and observe the same job again.
            with (case / 'progress-read-gaps.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'at_epoch': time.time(), 'file': progress.name,
                                         'error_type': 'JSONDecodeError', 'original_ci_restarted': False}) + '\n')
        else:
            if 'runs' in value:
                identities.update(row['id'] for row in value['runs'].values())
            else:
                identities.add(value['id'])
    return identities
