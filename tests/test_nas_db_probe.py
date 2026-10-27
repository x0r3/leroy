"""Database observation must not allocate another runtime in the API cgroup."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from diagnose_nas_release_group import POSTGRES_PROBE  # noqa: E402


@pytest.mark.parametrize('owner', ['leroy-nas-parity', 'unrelated-production'])
def test_database_probe_uses_only_owned_postgres_and_read_only_sql(monkeypatch, capsys, owner):
    calls = []

    def inspect(args, **kwargs):
        assert args == ['docker', 'inspect', 'leroy-nas-parity-postgres-1']
        return json.dumps([{'Id': 'owned-postgres', 'Config': {'Labels': {'com.docker.compose.project': owner}},
                            'State': {'Running': True}}])

    def query(args, **kwargs):
        calls.append(args)
        assert args[:3] == ['docker', 'exec', '-e']
        assert 'default_transaction_read_only=on' in args[3] and 'statement_timeout=3000' in args[3]
        assert args[4:6] == ['owned-postgres', 'psql']
        assert args[-1].startswith('SELECT ') and 'python' not in args
        return subprocess.CompletedProcess(args, 0, stdout='{"value":1,"statement_elapsed_seconds":0.001}', stderr='')

    monkeypatch.setattr(subprocess, 'check_output', inspect)
    monkeypatch.setattr(subprocess, 'run', query)
    if owner != 'leroy-nas-parity':
        with pytest.raises(AssertionError):
            exec(compile(POSTGRES_PROBE, 'db-probe', 'exec'), {})
        assert not calls
    else:
        exec(compile(POSTGRES_PROBE, 'db-probe', 'exec'), {})
        value = json.loads(capsys.readouterr().out)
        assert value['probe_location'] == 'postgres_container' and value['read_only'] is True
        assert value['statement_elapsed_seconds'] == 0.001


def test_database_probe_never_reports_raw_sql_errors(monkeypatch, capsys):
    monkeypatch.setattr(subprocess, 'check_output', lambda *a, **kw: json.dumps([
        {'Id': 'owned-postgres', 'Config': {'Labels': {'com.docker.compose.project': 'leroy-nas-parity'}}, 'State': {'Running': True}}
    ]))
    secret = 'PRIVATE_DATABASE_PASSWORD'
    monkeypatch.setattr(subprocess, 'run', lambda args, **kw: subprocess.CompletedProcess(args, 1, stdout=secret, stderr=secret))
    with pytest.raises(AssertionError) as error:
        exec(compile(POSTGRES_PROBE, 'db-probe', 'exec'), {})
    assert secret not in str(error.value) and secret not in capsys.readouterr().out
