import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from leroy import worker


class Clock:
    def __init__(self):
        self.now = 0
        self.stopped = False

    def is_set(self):
        return self.stopped

    def wait(self, seconds):
        self.now += seconds


@pytest.mark.parametrize("status", [401, 403, 409])
def test_heartbeat_fencing_cancels_immediately(monkeypatch, status):
    clock, cancelled, reason = Clock(), threading.Event(), ["Cancelled"]
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock.now)

    def send():
        request = httpx.Request("POST", "http://controller/heartbeat")
        httpx.Response(status, request=request).raise_for_status()

    worker.maintain_lease(send, clock, cancelled, reason)
    assert cancelled.is_set()
    assert clock.now == 0
    assert "rejected" in reason[0]


def test_failed_requests_count_towards_lease_deadline(monkeypatch):
    clock, cancelled, reason = Clock(), threading.Event(), ["Cancelled"]
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock.now)
    attempts = []

    def send():
        attempts.append(clock.now)
        clock.now += 5
        raise httpx.ReadTimeout("controller unavailable")

    worker.maintain_lease(send, clock, cancelled, reason)
    assert cancelled.is_set()
    assert 45 <= clock.now < 60
    assert len(attempts) > 1


def test_transport_diagnostic_retains_type_without_secret_exception_text(monkeypatch, capsys):
    clock, cancelled, reason = Clock(), threading.Event(), ["Cancelled"]
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock.now)

    def send():
        clock.now += 5
        raise httpx.ReadTimeout("private-token-in-an-exception")

    worker.maintain_lease(send, clock, cancelled, reason)
    output = capsys.readouterr().err
    assert cancelled.is_set() and "ReadTimeout" in reason[0] and "ReadTimeout" in output
    assert "private-token-in-an-exception" not in output and "private-token-in-an-exception" not in reason[0]


def test_transient_failure_recovers_then_server_cancellation_is_preserved(monkeypatch):
    clock, cancelled, reason = Clock(), threading.Event(), ["Cancelled"]
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock.now)
    replies = iter([503, {"cancel": False}, {"cancel": True, "reason": "Parent timed out"}])

    def send():
        reply = next(replies)
        if isinstance(reply, int):
            request = httpx.Request("POST", "http://controller/heartbeat")
            httpx.Response(reply, request=request).raise_for_status()
        if reply["cancel"]:
            clock.stopped = True
        return reply

    worker.maintain_lease(send, clock, cancelled, reason)
    assert cancelled.is_set()
    assert reason == ["Parent timed out"]
    assert clock.now == 9


@pytest.mark.parametrize("cancellation", ["Pipeline timeout exceeded", "Cancelled by operator"])
def test_cancellation_keeps_lease_alive_until_cleanup_finishes(monkeypatch, cancellation):
    clock, cancelled, reason = Clock(), threading.Event(), ["Cancelled"]
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock.now)
    confirmations = []

    def send():
        confirmations.append(clock.now)
        if clock.now >= 120:
            clock.stopped = True
        return {"cancel": True, "reason": cancellation}

    worker.maintain_lease(send, clock, cancelled, reason)
    assert cancelled.is_set()
    assert reason == [cancellation]
    assert confirmations[-1] >= 120, "Cleanup and artifact uploads must retain their lease"
    assert max(b - a for a, b in zip(confirmations, confirmations[1:], strict=False)) < 90


def test_cancelled_cleanup_still_stops_renewing_when_attempt_is_fenced(monkeypatch):
    clock, cancelled, reason = Clock(), threading.Event(), ["Cancelled"]
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock.now)
    confirmations = []

    def send():
        confirmations.append(clock.now)
        if clock.now >= 12:
            request = httpx.Request("POST", "http://controller/heartbeat")
            httpx.Response(409, request=request).raise_for_status()
        return {"cancel": True, "reason": "Pipeline timeout exceeded"}

    worker.maintain_lease(send, clock, cancelled, reason)
    assert confirmations[-1] == 12
    assert cancelled.is_set()
    assert "rejected" in reason[0]


def test_heartbeat_has_own_connection_pool_and_never_retries():
    reporter = worker.Reporter("http://controller", "run", "test-token")
    requests = []

    def unavailable(request):
        requests.append(request)
        raise httpx.ReadTimeout("unavailable")

    with httpx.Client(transport=httpx.MockTransport(unavailable), timeout=5) as client:
        reporter.heartbeat_client.close()
        reporter.heartbeat_client = client
        with pytest.raises(httpx.ReadTimeout):
            reporter.heartbeat()
        assert len(requests) == 1
        assert reporter.client is not reporter.heartbeat_client
    reporter.client.close()


def test_delayed_confirmation_does_not_restart_the_lease_clock(monkeypatch):
    clock, cancelled, reason = Clock(), threading.Event(), ["Cancelled"]
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock.now)

    def send():
        clock.now += 70
        return {"cancel": False}

    worker.maintain_lease(send, clock, cancelled, reason)
    assert cancelled.is_set()
    assert clock.now == 70


def test_docker_operations_have_a_timeout(monkeypatch):
    from leroy import runner

    def run(command, **kwargs):
        assert command == ["docker", "ps"]
        assert kwargs["timeout"] == 30
        raise runner.subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(runner.subprocess, "run", run)
    with pytest.raises(runner.subprocess.TimeoutExpired):
        runner.docker("ps")


def test_blocked_log_upload_cannot_starve_the_heartbeat_connection():
    entered, release = threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.path.endswith("/logs/build"):
                entered.set()
                release.wait(5)
                body = b'{"offset":4}'
            else:
                assert self.path.endswith("/heartbeat")
                body = b'{"cancel":false}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    reporter = worker.Reporter(f"http://127.0.0.1:{server.server_port}", "run", "test-token")
    reporter.client.close()
    reporter.client = httpx.Client(limits=httpx.Limits(max_connections=1), timeout=2)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            upload = pool.submit(reporter.send, "/logs/build", content=b"test")
            try:
                assert entered.wait(2)
                assert reporter.heartbeat() == {"cancel": False}
                assert not upload.done(), "Heartbeat must complete while the upload is still blocked"
            finally:
                release.set()
            assert upload.result(timeout=2) == {"offset": 4}
    finally:
        release.set()
        reporter.client.close()
        reporter.heartbeat_client.close()
        server.shutdown()
        server.server_close()
        serving.join(timeout=2)
