"""The optional observer must correlate all clients without retaining credentials."""

import collections
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "passive_http", Path(__file__).resolve().parents[1] / "scripts/diagnostics/nas-passive-http.py"
)
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


def message(first, body, authorization=None):
    headers = [first, "Content-Length: " + str(len(body))]
    if authorization:
        headers.append("Authorization: Bearer " + authorization)
    return ("\r\n".join(headers) + "\r\n\r\n").encode() + body


def test_fragmented_logins_and_commands_bind_accounts_without_secrets():
    rows, pending = [], collections.deque()
    identities = observer.ClientIdentities()
    request = observer.HttpStream(True, rows.append, pending, lambda: len(rows), identities)
    response = observer.HttpStream(False, rows.append, pending, lambda: len(rows), identities)
    login = message("POST /api/v1/auth/login HTTP/1.1", json.dumps({"username": "PRIVATE_USER", "password": "PRIVATE_PASSWORD"}).encode())
    for byte in login:
        request.feed(bytes([byte]), 1)
    response.feed(message("HTTP/1.1 200 OK", b'{"token":"PRIVATE_TOKEN"}'), 2)
    command = message("POST /api/v1/commands HTTP/1.1", b'{"command":"getDevEnvironmentTreeBootstrap","clientId":"PRIVATE_CLIENT","args":{"secret":"PRIVATE_ARGUMENT"}}', "PRIVATE_TOKEN")
    request.feed(command, 3)
    binding, = (row for row in rows if row["kind"] == "login-binding")
    observed = rows[-1]
    assert observed["principal"] == binding["principal"]
    assert observed["client"] == identities.digest("PRIVATE_CLIENT")
    assert observed["command"] == "getDevEnvironmentTreeBootstrap"
    assert "PRIVATE_" not in json.dumps(rows)
    assert binding["account"] == identities.digest("PRIVATE_USER")


def test_pseudonyms_are_not_reusable_between_diagnostic_runs():
    first, second = observer.ClientIdentities(), observer.ClientIdentities()
    assert first.digest("token") != second.digest("token")


def test_disabled_mode_keeps_existing_metadata_schema():
    rows = []
    request = observer.HttpStream(True, rows.append, collections.deque(), lambda: 1)
    request.feed(message("POST /api/v1/commands HTTP/1.1", b'{"command":"getInfo","clientId":"PRIVATE_CLIENT"}', "PRIVATE_TOKEN"), 1)
    assert "principal" not in rows[0] and "client" not in rows[0]
    assert "PRIVATE_" not in json.dumps(rows)


def test_cookie_browser_identity_survives_reload_without_credentials():
    rows, pending = [], collections.deque()
    key = b'x' * 32
    identities = observer.ClientIdentities(key)
    request = observer.HttpStream(True, rows.append, pending, lambda: len(rows), identities)
    response = observer.HttpStream(False, rows.append, pending, lambda: len(rows), identities)
    request.feed(message('POST /api/v1/browser/session HTTP/1.1', b'{"username":"PRIVATE_USER","password":"PRIVATE_PASSWORD"}'), 1)
    response.feed(b'HTTP/1.1 200 OK\r\nSet-Cookie: __Host-graphato-session=PRIVATE_COOKIE; Path=/; HttpOnly\r\nContent-Length: 0\r\n\r\n', 2)
    binding, = (row for row in rows if row['kind'] == 'browser-session-binding')
    request.feed(b'POST /api/v1/commands HTTP/1.1\r\nCookie: __Host-graphato-session=PRIVATE_COOKIE\r\nContent-Length: 21\r\n\r\n{"command":"getInfo"}', 3)
    assert rows[-1]['browser_principal'] == binding['browser_principal']
    assert observer.ClientIdentities(key).digest('PRIVATE_COOKIE') == binding['browser_principal']
    assert binding['account'] == identities.digest('PRIVATE_USER')
    assert 'PRIVATE_' not in json.dumps(rows)
