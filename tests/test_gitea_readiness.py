import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from leroy.actions import gitea_bootstrap


@contextmanager
def target(ready_after):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            requests.append(self.path)
            if self.path == "/api/v1/version":
                ready = requests.count(self.path) > ready_after
                self.send_response(200 if ready else 503)
                self.end_headers()
                self.wfile.write(b'{"version":"1.23.7"}')
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"name": "example"}).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def context(url, seconds):
    return {
        "parameters": {
            "GITEA_URL": url,
            "GITEA_CONTAINER_NAME": "unused",
            "ENSURE_GITEA_ADMIN_LOGIN": False,
            "GITEA_WAIT_SECONDS": seconds,
            "GITEA_OWNER": "test",
            "GITEA_REPO": "example",
        }
    }


def test_starting_gitea_recovers_before_repository_request(monkeypatch):
    monkeypatch.setenv("GITEA_ADMIN_USER", "test")
    monkeypatch.setenv("GITEA_ADMIN_PASSWORD", "test-password")
    with target(ready_after=1) as (url, requests):
        result = gitea_bootstrap(context(url, 3))
    assert result == {"repository": "test/example", "created": False}
    assert requests == ["/api/v1/version", "/api/v1/version", "/api/v1/repos/test/example"]


def test_unready_gitea_times_out_without_repository_request(monkeypatch):
    monkeypatch.setenv("GITEA_ADMIN_USER", "test")
    monkeypatch.setenv("GITEA_ADMIN_PASSWORD", "test-password")
    with target(ready_after=100) as (url, requests):
        with pytest.raises(TimeoutError, match="GITEA_WAIT_SECONDS"):
            gitea_bootstrap(context(url, 1))
    assert requests and all(path == "/api/v1/version" for path in requests)
