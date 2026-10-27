"""Slow Docker startup must retain ownership without running a fenced attempt."""
import subprocess
import threading
from types import SimpleNamespace

import pytest

from leroy import runner


def lease(monkeypatch, send=None):
    calls = []
    reporter = SimpleNamespace(
        heartbeat=send or (lambda: calls.append("heartbeat")),
        client=SimpleNamespace(close=lambda: calls.append("close-client")),
        heartbeat_client=SimpleNamespace(close=lambda: calls.append("close-heartbeat")),
    )
    monkeypatch.setattr(runner, "Reporter", lambda *args: reporter)
    guard = runner.StartupLease("http://controller", {"id": "a" * 32, "token": "private-token"}, threading.Event())
    return guard, calls


def test_slow_creation_keeps_renewing_until_worker_handoff(monkeypatch):
    renewed = threading.Event()
    heartbeats = []

    def heartbeat():
        heartbeats.append(1)
        if len(heartbeats) >= 2:
            renewed.set()
        return {"cancel": False}

    def monitor(send, stop, cancelled, reason):
        while not stop.is_set():
            send()
            stop.wait(0.01)

    monkeypatch.setattr(runner, "maintain_lease", monitor)
    guard, calls = lease(monkeypatch, heartbeat)
    docker_calls = []

    def docker(*args, timeout):
        docker_calls.append((args, timeout))
        assert renewed.wait(2), "Lease renewal must continue while Docker preparation is blocked"
        return SimpleNamespace(stdout="container-id")

    monkeypatch.setattr(runner, "docker", docker)
    guard.start()
    try:
        guard.docker("container creation", "create", "--env", "TOKEN=private-token", timeout=120)
        guard.docker("container start", "start", "owned-container", timeout=120)
    finally:
        guard.close()
    assert not guard.thread.is_alive()
    assert [timeout for _, timeout in docker_calls] == [120, 120]
    assert calls == ["close-client", "close-heartbeat"]
    # Closing the supervisor monitor must leave the handed-off container alone.
    assert all(args[0] not in {"stop", "rm"} for args, _ in docker_calls)


def test_cancellation_during_creation_prevents_worker_start(monkeypatch):
    guard, _ = lease(monkeypatch)
    commands = []

    def docker(*args, timeout):
        commands.append(args[0])
        guard.cancelled.set()
        return SimpleNamespace(stdout="created-late")

    monkeypatch.setattr(runner, "docker", docker)
    try:
        with pytest.raises(runner.StartupCancelled):
            guard.docker("container creation", "create", timeout=120)
        with pytest.raises(runner.StartupCancelled):
            guard.docker("container start", "start", timeout=120)
    finally:
        guard.close()
    assert commands == ["create"]


def test_supervisor_shutdown_prevents_any_new_docker_call(monkeypatch):
    guard, _ = lease(monkeypatch)
    guard.supervisor_stop.set()
    monkeypatch.setattr(runner, "docker", lambda *args, **kwargs: pytest.fail("Startup already stopped"))
    try:
        with pytest.raises(runner.StartupCancelled):
            guard.docker("container start", "start", timeout=120)
    finally:
        guard.close()


@pytest.mark.parametrize("exception", [
    subprocess.TimeoutExpired(["docker", "create", "TOKEN=private-token"], 120, stderr="private-key"),
    subprocess.CalledProcessError(1, ["docker", "create", "TOKEN=private-token"], stderr="private-key"),
])
def test_failure_reports_operation_without_credentials(monkeypatch, exception):
    guard, _ = lease(monkeypatch)
    guard.phase = "container creation"
    try:
        reason = guard.failure_reason(exception)
    finally:
        guard.close()
    assert "container creation" in reason and type(exception).__name__ in reason
    assert "private-token" not in reason and "private-key" not in reason and "TOKEN=" not in reason
    if isinstance(exception, subprocess.TimeoutExpired):
        assert "120s" in reason


def test_startup_inspection_keeps_short_default_and_cleanup_is_idempotent(monkeypatch):
    guard, calls = lease(monkeypatch)
    monkeypatch.setattr(runner, "docker", lambda *args, timeout: SimpleNamespace(stdout=str(timeout)))
    try:
        assert guard.docker("image inspection", "image", "inspect", "local-image").stdout == "30"
    finally:
        guard.close()
        guard.close()
    assert calls == ["close-client", "close-heartbeat"]
