"""A revoked real HTTP session must also close an already connected event stream."""

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import httpx
from test_support import api

with closing(api()) as client:
    run = client.get("/api/runs?status=succeeded&limit=1").json()[0]
    ready = threading.Event()

    def listen():
        with httpx.Client(base_url=str(client.base_url), cookies=client.cookies, timeout=10) as stream_client:
            with stream_client.stream("GET", "/api/runs/" + run["id"] + "/stream") as stream:
                stream.raise_for_status()
                ready.set()
                for line in stream.iter_lines():
                    if line == "event: session-expired":
                        return True
        return False

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(listen)
        assert ready.wait(10)
        client.post("/api/auth/logout").raise_for_status()
        assert result.result(timeout=10)
        assert client.get("/api/auth/me").status_code == 401
    print("Revoking the HTTP session terminated its live event stream")
