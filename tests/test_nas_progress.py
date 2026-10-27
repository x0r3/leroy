"""Partial progress must never interrupt or replay an original CI job."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_progress as progress  # noqa: E402


def test_readers_keep_previous_complete_snapshot_until_publication(monkeypatch, tmp_path):
    path = tmp_path / 'leroy-progress.json'
    path.write_text(json.dumps({'id': 'original', 'status': 'running'}))
    replace = progress.os.replace

    def paused_publication(source, destination):
        assert json.loads(path.read_text()) == {'id': 'original', 'status': 'running'}
        assert json.loads(Path(source).read_text()) == {'id': 'original', 'status': 'failed'}
        replace(source, destination)

    monkeypatch.setattr(progress.os, 'replace', paused_publication)
    progress.publish(path, {'id': 'original', 'status': 'failed'})
    assert json.loads(path.read_text())['status'] == 'failed'
    assert list(tmp_path.iterdir()) == [path]


def test_failed_publication_keeps_last_complete_progress(monkeypatch, tmp_path):
    path = tmp_path / 'leroy-progress.json'
    path.write_text('{"id":"original"}')

    def failure(*args):
        raise OSError('Storage unavailable')

    monkeypatch.setattr(progress.os, 'replace', failure)
    with pytest.raises(OSError):
        progress.publish(path, {'id': 'original', 'status': 'running'})
    assert json.loads(path.read_text()) == {'id': 'original'}
    assert list(tmp_path.iterdir()) == [path]


def test_busy_windows_reader_can_close_before_metadata_publication(monkeypatch, tmp_path):
    path = tmp_path / 'progress.json'
    replace, attempts = progress.os.replace, []

    def busy(source, destination):
        attempts.append(1)
        if len(attempts) == 1:
            raise PermissionError('Reader is still open')
        replace(source, destination)

    monkeypatch.setattr(progress.os, 'replace', busy)
    monkeypatch.setattr(progress.time, 'sleep', lambda *args: None)
    progress.publish(path, {'id': 'same-run'})
    assert len(attempts) > 1 and json.loads(path.read_text()) == {'id': 'same-run'}


@pytest.mark.parametrize('partial', ['', '{', '{"runs":'])
def test_incomplete_progress_retains_the_authoritative_start_id(tmp_path, partial):
    (tmp_path / 'leroy-start.json').write_text('{"id":"same-original"}')
    (tmp_path / 'leroy-progress.json').write_text(partial)
    assert progress.run_ids(tmp_path) == {'same-original'}
    gap = json.loads((tmp_path / 'progress-read-gaps.jsonl').read_text())
    assert gap['error_type'] == 'JSONDecodeError' and not gap['original_ci_restarted']


def test_full_tree_retains_parent_and_all_child_ids(tmp_path):
    (tmp_path / 'leroy-start.json').write_text('{"id":"parent"}')
    (tmp_path / 'leroy-progress.json').write_text('{"runs":{"parent":{"id":"parent"},"child":{"id":"child"}}}')
    assert progress.run_ids(tmp_path) == {'parent', 'child'}


def test_uncertain_dispatch_marker_cannot_authorize_another_run(tmp_path):
    (tmp_path / 'leroy-start.json').write_text('{')
    with pytest.raises(json.JSONDecodeError):
        progress.run_ids(tmp_path)
