"""A full OS output pipe must not stall ASGI requests or graceful shutdown."""

import json
import os
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import httpx
import pytest

PROGRAM = r'''
import logging,sys,uvicorn
from fastapi import FastAPI
if sys.argv[2]=='bounded':
 from leroy.console_logging import logging_config
app=FastAPI()
server=None
@app.get('/health/live')
async def health():return {'ok':True}
@app.post('/flood')
async def flood():
 for _ in range(2048):logging.getLogger(sys.argv[3]).warning('PIPE PRESSURE '+'x'*1024)
 return {'ok':True}
@app.post('/shutdown')
async def shutdown():
 server.should_exit=True
 return {'ok':True}
config=uvicorn.Config(app,host='127.0.0.1',port=int(sys.argv[1]),
 log_config=logging_config() if sys.argv[2]=='bounded' else uvicorn.config.LOGGING_CONFIG)
server=uvicorn.Server(config)
server.run()
'''


@pytest.mark.parametrize("mode", ["legacy", "bounded"])
@pytest.mark.parametrize("logger", ["uvicorn.error", "dependency"])
def test_real_uvicorn_full_console_pipe_keeps_health_and_shutdown_responsive(tmp_path, mode, logger):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    script = tmp_path / "pipe_server.py"
    script.write_text(textwrap.dedent(PROGRAM))
    environment = dict(os.environ)
    source = Path(__file__).resolve().parents[1] / "src"
    environment["PYTHONPATH"] = str(source) + os.pathsep + environment.get("PYTHONPATH", "")
    process = subprocess.Popen([sys.executable, "-B", str(script), str(port), mode, logger],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=1, trust_env=False) as api:
            until = time.monotonic() + 15
            while True:
                try:
                    assert api.get("/health/live").status_code == 200
                    break
                except httpx.TransportError:
                    assert process.poll() is None, "Test server exited before readiness"
                    assert time.monotonic() < until, "Test server failed to start"
                    time.sleep(0.05)
            if mode == "legacy":
                with pytest.raises(httpx.ReadTimeout):
                    api.post("/flood")
                with pytest.raises(httpx.ReadTimeout):
                    api.get("/health/live")
            else:
                assert api.post("/flood").status_code == 200
                assert api.get("/health/live").status_code == 200
                assert api.post("/shutdown").status_code == 200
                assert process.wait(timeout=5) == 0, "Console backpressure blocked process shutdown"
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


def test_console_worker_formats_bounds_and_reports_drops_after_sink_recovers():
    import logging
    import threading

    from leroy.console_logging import NonBlockingStreamHandler

    class Sink:
        def __init__(self):
            self.started = threading.Event()
            self.release = threading.Event()
            self.lines = []

        def write(self, value):
            self.started.set()
            assert self.release.wait(3)
            self.lines.append(value)

        def flush(self):
            pass

    sink = Sink()
    handler = NonBlockingStreamHandler(sink, capacity=2, max_bytes=128)
    try:
        record = logging.LogRecord("probe", logging.INFO, __file__, 1, "Meldung ä " * 100, (), None)
        handler.handle(record)
        assert sink.started.wait(1)
        for _ in range(20):
            handler.handle(record)
        assert handler.dropped_records > 0
        handler.flush()  # Must not wait for the sink.
        sink.release.set()
        until = time.monotonic() + 2
        while not any("dropped" in line for line in sink.lines) and time.monotonic() < until:
            time.sleep(0.01)
        assert any("dropped" in line for line in sink.lines)
        assert all(len(line.encode()) <= 128 for line in sink.lines if "[truncated]" in line)
        assert handler.write_errors == 0
    finally:
        sink.release.set()
        handler.close()
        handler.writer.join(timeout=1)


def test_logging_configuration_does_not_mutate_uvicorn_defaults():
    from uvicorn.config import LOGGING_CONFIG

    from leroy.console_logging import logging_config

    before = json.dumps(LOGGING_CONFIG, sort_keys=True)
    configured = logging_config()
    assert all(h['class'] == 'leroy.console_logging.NonBlockingStreamHandler' for h in configured['handlers'].values())
    assert json.dumps(LOGGING_CONFIG, sort_keys=True) == before
