"""Frozen source validation must distinguish Windows checkout conversion from edits."""

import hashlib
import importlib
import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    helper = importlib.import_module("finish_frozen_master_nas_acceptance")
    checkout = tmp_path / "checkout"
    checkout.mkdir()

    def git(*args):
        return subprocess.check_output(["git", "-C", str(checkout), *args]).decode().strip()

    git("init", "-q")
    for key, value in {"user.name": "Source validation", "user.email": "source-test@example.invalid",
                       "commit.gpgsign": "false", "core.autocrlf": "false"}.items():
        git("config", key, value)
    files = {name: b"pipeline {\n  agent any\n}\n" for name in (
        "Jenkinsfile", "Jenkinsfile.acceptance", "Jenkinsfile.postdeploy-web", "Jenkinsfile.postdeploy-quality")}
    for name, data in files.items():
        (checkout / name).write_bytes(data)
    git("add", ".")
    git("commit", "-q", "-m", "Isolated source validation fixture")
    commit = git("rev-parse", "HEAD")
    folder = tmp_path / "evidence"
    folder.mkdir()
    (folder / "frozen-master.json").write_text(json.dumps({
        "checkout": "checkout", "tree": git("rev-parse", "HEAD^{tree}"),
        "jenkinsfiles_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }))
    monkeypatch.setattr(helper, "ROOT", tmp_path)
    monkeypatch.setattr(helper, "candidate_checkout", lambda _commit: checkout)
    return helper, folder, checkout, commit, git, files


def test_clean_windows_conversion_preserves_exact_frozen_blobs(frozen):
    helper, folder, checkout, commit, git, files = frozen
    git("config", "core.autocrlf", "true")
    for name in files:
        (checkout / name).unlink()
    git("checkout", "--", *files)
    assert not git("status", "--porcelain")
    assert all(b"\r\n" in (checkout / name).read_bytes() for name in files)
    proof = json.loads(helper.confirm_frozen_source(folder, commit).read_text())
    assert proof["clean_checkout"] and proof["jenkinsfile_hashes_match"]
    assert all(row["working_crlf_conversion"] for row in proof["jenkinsfiles"].values())
    assert not proof["source_changed"]


def test_actual_source_edit_is_rejected(frozen):
    helper, folder, checkout, commit, _git, _files = frozen
    (checkout / "Jenkinsfile").write_text("pipeline { changed_source }\n")
    with pytest.raises(AssertionError):
        helper.confirm_frozen_source(folder, commit)
    assert not (folder / "frozen-integrity-final.json").exists()


def test_committed_wrong_frozen_digest_is_rejected(frozen):
    helper, folder, _checkout, commit, _git, _files = frozen
    path = folder / "frozen-master.json"
    value = json.loads(path.read_text())
    value["jenkinsfiles_sha256"]["Jenkinsfile"] = "0" * 64
    path.write_text(json.dumps(value))
    with pytest.raises(AssertionError):
        helper.confirm_frozen_source(folder, commit)
    assert not (folder / "frozen-integrity-final.json").exists()
