"""The remote lease observer must retain timing without arbitrary job secrets."""
import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from observe_nas_release_jobs import PROGRAM  # noqa: E402


@pytest.mark.parametrize("log_status", [0, 1])
def test_remote_lease_observer_filters_sensitive_logs(monkeypatch, capsys, log_status):
    run = "a" * 32
    name = "leroy-" + run
    secret = "private-token-and-url-must-not-be-retained"
    outer = {"Id": "own-daemon", "Config": {"Labels": {"com.docker.compose.project": "leroy-nas-parity"}}}
    worker = {
        "Config": {"Labels": {"io.leroy.runner": "runner-nas-parity"}, "Env": ["TOKEN=" + secret]},
        "State": {"Running": True, "OOMKilled": False, "ExitCode": 0}, "Image": "sha256:fixture",
    }

    def output(args, **kwargs):
        if args == ["docker", "inspect", "leroy-nas-parity-docker-1"]:
            return json.dumps([outer])
        assert args[:4] == ["docker", "exec", "own-daemon", "docker"]
        if args[4] == "ps":
            assert "label=io.leroy.runner=runner-nas-parity" in args
            return name + "\n"
        assert args[4:] == ["inspect", name]
        return json.dumps([worker])

    def logs(args, **kwargs):
        assert args == ["docker", "exec", "own-daemon", "docker", "logs", "--timestamps", "--tail", "100", "--since", "120s", name]
        return subprocess.CompletedProcess(args, log_status, stdout=(
            "2026-10-12T21:34:21.123456789Z Leroy lease renewal failed: ReadTimeout; seconds since confirmation: 40.125\n"
            "2026-10-12T21:34:26Z Leroy lease stopped: Controller lease could not be renewed (last failure: ReadTimeout)\n"
            "2026-10-12T21:34:22Z arbitrary output " + secret + "\n"
            "2026-10-12T21:34:22Z Leroy lease renewal failed: HTTP 500 response=" + secret + "\n"
            '2026-10-12T21:34:25Z Leroy lease timing: {"event":"slow_confirmation","request_seconds":51.2,"previous_confirmation_age_seconds":3}\n'
            '2026-10-12T21:34:25Z Leroy lease timing: {"event":"local_deadline","unconfirmed_seconds":51.2,"last_request_seconds":51.2,"loop_gap_seconds":3}\n'
            '2026-10-12T21:34:25Z Leroy lease timing: {"event":"slow_confirmation","request_seconds":"' + secret + '","previous_confirmation_age_seconds":3}\n'
        ), stderr="Error: " + secret)

    original_is_file = pathlib.Path.is_file
    monkeypatch.setattr(pathlib.Path, "is_file", lambda p: True if p.as_posix() == "/volume1/docker/leroy-nas-parity/.leroy-owned" else original_is_file(p))
    monkeypatch.setattr(subprocess, "check_output", output)
    monkeypatch.setattr(subprocess, "run", logs)
    exec(compile(PROGRAM, "owned-lease-observer", "exec"), {})
    captured = capsys.readouterr().out
    assert secret not in captured
    result = json.loads(captured)
    row = result["owned_jobs"][0]
    assert row["log_read_succeeded"] is (log_status == 0)
    assert row["lease_diagnostics_with_timestamps"] == [
        {"at": "2026-10-12T21:34:21.123456789Z", "message": "Leroy lease renewal failed: ReadTimeout; seconds since confirmation: 40.125"},
        {"at": "2026-10-12T21:34:26Z", "message": "Leroy lease stopped: Controller lease could not be renewed (last failure: ReadTimeout)"},
    ]
    assert row["lease_diagnostics"] == [event["message"] for event in row["lease_diagnostics_with_timestamps"]]
    assert row['lease_timing_diagnostics'] == [
        {'at': '2026-10-12T21:34:25Z', 'event': 'slow_confirmation', 'request_seconds': 51.2, 'previous_confirmation_age_seconds': 3},
        {'at': '2026-10-12T21:34:25Z', 'event': 'local_deadline', 'unconfirmed_seconds': 51.2, 'last_request_seconds': 51.2, 'loop_gap_seconds': 3},
    ]
    assert result["arbitrary_logs_retained"] is False
