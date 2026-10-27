"""Transport evidence must distinguish phases without leaking request secrets."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from leroy import lease_trace


def test_actual_httpcore_events_are_numeric_and_do_not_include_request_data(capsys):
    secret = 'private-authorization-and-path'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"cancel": false}')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(trust_env=False) as client, lease_trace.LeaseTransportTrace(threshold_seconds=0) as trace:
            response = client.post('http://127.0.0.1:' + str(server.server_port) + '/' + secret,
                                   headers={'Authorization': 'Bearer ' + secret}, json={'secret': secret},
                                   extensions={'trace': trace})
            assert response.json() == {'cancel': False}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    output = capsys.readouterr().err
    assert secret not in output and 'Authorization' not in output and '127.0.0.1' not in output
    value = json.loads(output.removeprefix('Leroy lease transport: '))
    assert not value['request_failed']
    assert {'connect', 'send_headers', 'receive_headers', 'receive_body'} <= value['phases_seconds'].keys()
    assert all(type(n) is float and n >= 0 for n in value['phases_seconds'].values())


def test_failed_request_retains_exception_semantics_without_exception_text(capsys):
    secret = 'private-token-and-host'
    with pytest.raises(httpx.ConnectTimeout, match=secret), lease_trace.LeaseTransportTrace():
        raise httpx.ConnectTimeout(secret)
    output = capsys.readouterr().err
    assert secret not in output
    assert json.loads(output.removeprefix('Leroy lease transport: '))['request_failed']


def test_slow_phase_keeps_wall_time_separate_from_thread_cpu(monkeypatch, capsys):
    clock = [0]
    monkeypatch.setattr(lease_trace.time, 'monotonic', lambda: clock[0])
    with lease_trace.LeaseTransportTrace() as trace:
        clock[0] = 1
        trace('connection.connect_tcp.started', {'host': 'private', 'timeout': 3})
        clock[0] = 7
        trace('connection.connect_tcp.complete', {'return_value': 'private'})
        trace('private.unsupported.started', {'Authorization': 'private'})
        clock[0] = 8
    value = json.loads(capsys.readouterr().err.removeprefix('Leroy lease transport: '))
    assert value['wall_seconds'] == 8 and value['phases_seconds'] == {'connect': 6}
    assert value['thread_cpu_seconds'] < 1
    assert value['last_event'] == 'connect.complete'


def test_fast_success_is_silent(capsys):
    with lease_trace.LeaseTransportTrace():
        pass
    assert capsys.readouterr().err == ''


def test_diagnostic_output_failure_does_not_fail_the_request(monkeypatch):
    def broken(*args, **kwargs):
        raise BrokenPipeError('private output error')

    monkeypatch.setattr('builtins.print', broken)
    with lease_trace.LeaseTransportTrace(threshold_seconds=0):
        pass


def test_thread_identity_records_routing_flags_without_host_or_proxy_credentials(monkeypatch, capsys):
    secret = 'private-secret'
    monkeypatch.setenv('HTTP_PROXY', 'http://user:' + secret + '@private-proxy:3128')
    lease_trace.announce_thread('http://user:' + secret + '@private-host:8088/internal/private-path')
    output = capsys.readouterr().err
    assert all(word not in output for word in (secret, 'private-proxy', 'private-host', 'private-path'))
    value = json.loads(output.removeprefix('Leroy lease transport: '))
    assert value['proxy_environment_present'] and value['pid'] > 0 and value['thread_id'] > 0
