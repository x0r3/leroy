import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from leroy.catalog import catalog
from leroy.scheduler import next_due
from leroy.schema import Parameter, Pipeline, Step
from leroy.worker import Redactor


def test_inventory_matches_live_job_set():
    inventory = json.loads(Path("docs/jenkins-inventory.json").read_text())
    migrated = list(catalog())
    assert {p.id for p in migrated} == {j["name"] for j in inventory["jobs"]}
    assert len(migrated) == 13
    assert all(len(p.source["script_sha256"]) == 64 for p in migrated)


def test_cycles_and_unknown_dependencies_are_rejected():
    with pytest.raises(ValueError, match="cycle"):
        Pipeline(
            id="cycle",
            name="cycle",
            steps=[Step(id="a", name="A", needs=["b"]), Step(id="b", name="B", needs=["a"])],
        )
    with pytest.raises(ValueError, match="Unknown"):
        Pipeline(id="missing", name="missing", steps=[Step(id="a", name="A", needs=["gone"])])


def test_parameters_enforce_types_and_revision_before_execution():
    acceptance = next(p for p in catalog() if p.id == "graphato-release-acceptance")
    with pytest.raises(ValueError):
        acceptance.bind({"RELEASE_COMMIT": "master; whoami"})
    with pytest.raises(ValueError):
        acceptance.bind({"RELEASE_COMMIT": "a" * 40, "UNKNOWN": "secret"})
    with pytest.raises(ValueError):
        Parameter(name="DRY_RUN", kind="boolean").validate_value("false")


def test_all_chunk_boundaries_redact_complete_secret():
    original = b"before very-secret-password after"
    for boundary in range(len(original) + 1):
        redactor = Redactor(["very-secret-password"])
        output = (
            redactor.feed(original[:boundary])
            + redactor.feed(original[boundary:])
            + redactor.feed(b"", final=True)
        )
        assert output == b"before [REDACTED] after"
    redactor = Redactor(["very-secret-password"])
    output = b"".join(redactor.feed(bytes([byte])) for byte in original) + redactor.feed(b"", final=True)
    assert output == b"before [REDACTED] after"


def test_sparse_progress_is_not_delayed_by_long_credentials():
    redactor = Redactor(["-----BEGIN KEY-----" + "private" * 1000])
    assert redactor.feed(b"Post-deployment web: browser-core\n") == b"Post-deployment web: browser-core\n"
    assert redactor.pending == b""


@pytest.mark.parametrize(
    "secrets,source,expected",
    [
        (["abc", "bcd"], b"!abcd!", b"![REDACTED]!"),
        (["abcdef", "cd"], b"!abcdef cd!", b"![REDACTED] [REDACTED]!"),
        (["aaa"], b"!aaaaaaaaaa!", b"![REDACTED]!"),
        (["key", "long-key-value"], b"!long-key-value key!", b"![REDACTED] [REDACTED]!"),
    ],
)
def test_overlapping_secrets_remain_masked_at_every_split(secrets, source, expected):
    for first in range(len(source) + 1):
        for second in range(first, len(source) + 1):
            redactor = Redactor(secrets)
            output = (
                redactor.feed(source[:first])
                + redactor.feed(source[first:second])
                + redactor.feed(source[second:], final=True)
            )
            assert output == expected


def test_repeated_secret_overlaps_cannot_grow_the_stream_buffer():
    redactor = Redactor(["aaa"])
    output = b""
    for _ in range(100):
        output += redactor.feed(b"a" * 100)
        assert len(redactor.pending) <= 2
    assert output + redactor.feed(b"", final=True) == b"[REDACTED]"


def test_hashed_schedule_is_stable_and_timezone_aware():
    spec = next(p for p in catalog() if p.id == "music-library-sync-smartphone").model_dump()
    date = datetime(2026, 10, 2, tzinfo=timezone.utc)
    assert next_due(spec, date) == next_due(spec, date)
    assert next_due(spec, date).hour == 3
    assert next_due(spec, date).tzinfo is not None


def test_scheduler_preserves_ssh_file_paths_and_reads_http_secret_values(tmp_path):
    from leroy.git_auth import git_environment
    from leroy.scheduler import scm_credentials

    key = tmp_path / "private_key"
    known = tmp_path / "known_hosts"
    password = tmp_path / "password"
    key.write_text("private key contents")
    known.write_text("pinned host key")
    password.write_text("secret-password\n")
    credentials = scm_credentials(
        {
            "scm_credentials": {
                "test": {
                    "GIT_SSH_KEY_FILE": str(key),
                    "GIT_KNOWN_HOSTS": str(known),
                    "GIT_PASSWORD": str(password),
                }
            }
        },
        "test",
    )
    assert credentials["GIT_PASSWORD"] == "secret-password"
    with git_environment(credentials) as env:
        assert str(key) in env["GIT_SSH_COMMAND"]
        assert str(known) in env["GIT_SSH_COMMAND"]
        assert "private key contents" not in env["GIT_SSH_COMMAND"]


def test_deployment_policies_preserved():
    jobs = {p.id: p for p in catalog()}
    assert jobs["antares-ci"].concurrency == "replace"
    assert jobs["graphato-ci"].concurrency == "serial"
    acceptance = jobs["graphato-release-acceptance"]
    assert [s.options["pipeline"] for s in acceptance.steps if s.action == "child"] == [
        "graphato-postdeploy-web",
        "graphato-postdeploy-quality",
    ]
    assert acceptance.steps[-1].always
    assert acceptance.timeout == 480 * 60
    for step in acceptance.steps:
        if step.action == "child":
            # Jenkins permits seven hours per suite. The waiting parent step
            # must not impose Step's unrelated thirty-minute default.
            assert step.timeout == jobs[step.options["pipeline"]].timeout == 420 * 60
    for pipeline_id, step_id, seconds in [
        ("music-library-sync-smartphone", "sync", 7200),
        ("nikicas-hub-bootstrap-host", "bootstrap", 7200),
        ("graphato-bootstrap-host", "bootstrap", 3600),
        ("graphato-ci", "deploy", 14400),
    ]:
        assert next(s.timeout for s in jobs[pipeline_id].steps if s.id == step_id) == seconds
    assert all(not p.enabled for p in jobs.values())


def test_retention_keeps_complete_families_and_active_work():
    from datetime import timedelta
    from types import SimpleNamespace

    from leroy.db import now
    from leroy.maintenance import retention_candidates

    old = now() - timedelta(days=30)

    def row(id, number, parent=None, retry=None, status="succeeded"):
        return SimpleNamespace(
            id=id,
            number=number,
            pipeline_id=id.split("-")[0],
            parent_id=parent,
            retry_of=retry,
            status=status,
            created_at=old,
        )

    rows = [
        row("a-old", 1),
        row("a-parent", 2),
        row("b-child", 3, parent="a-parent"),
        row("a-latest", 4, retry="a-parent"),
        row("b-active", 5, status="running"),
    ]
    assert retention_candidates(rows, {"a": 1, "b": 1}, now() - timedelta(days=7)) == ["a-old"]


@pytest.mark.parametrize(
    "changes",
    [
        {"timezone": "Missing/Timezone"},
        {"schedule": "not cron"},
        {"schedule": "* * * * * *"},
        {"poll_seconds": 60},
        {"parameters": [{"name": "N", "kind": "integer", "default": "bad"}]},
        {"parameters": [{"name": "N", "pattern": "["}]},
    ],
)
def test_bad_configuration_is_rejected_at_publication(changes):
    with pytest.raises(ValueError):
        Pipeline(id="test", name="test", steps=[Step(id="work", name="Work")], **changes)


def test_child_parameters_are_explicit_and_repository_independent():
    from leroy.worker import child_inputs

    context = {
        "run": {"commit": "a" * 40},
        "values": {"artifact": "report"},
        "parameters": {"TARGET": "test"},
    }
    step = Step(
        id="child",
        name="Child",
        action="child",
        options={
            "pipeline": "anything",
            "parameters": {"mode": "check"},
            "parameter_sources": {
                "target": "parameters.TARGET",
                "file": "values.artifact",
                "revision": "commit",
            },
        },
    )
    result = child_inputs(step, context)
    assert result["parameters"] == {"mode": "check", "target": "test", "file": "report", "revision": "a" * 40}
    assert result["step_id"] == "child"
    step.options = {"pipeline": "anything", "inherit_commit": False}
    assert child_inputs(step, context) == {"step_id": "child", "parameters": {}, "commit": None}
