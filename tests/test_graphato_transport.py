"""Graphato's checkout owns SSH policy and failure recovery, as in Jenkins."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from leroy import actions


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setenv('DEPLOY_KEY', str(tmp_path / 'identity'))
    monkeypatch.setenv('KNOWN_HOSTS', str(tmp_path / 'known_hosts'))
    return {'repo': str(tmp_path / 'repo'), 'work': str(tmp_path), 'results': str(tmp_path),
            'profile': {'graphato': {'host': 'isolated-target', 'port': 2207,
                                    'desktop_releases': '/releases'}},
            'run': {'id': 'run-id', 'number': 123}, 'parameters': {},
            'values': {'commit': 'a' * 40, 'build_timestamp': '20261016090000'},
            'step': {'options': {'command': 'postdeploy', 'suite': 'quality'}}}


def test_graphato_preserves_checkout_options_and_pinned_endpoint(context, monkeypatch):
    seen = []
    upstream = SimpleNamespace()
    options = ['-o', 'ServerAliveCountMax=4', '-o', 'ForwardAgent=no', '-o', 'ClearAllForwardings=yes']

    def ssh_options(args):
        seen.append(args)
        return list(options)

    def load(path, name):
        if Path(path).name == 'ci.py':
            return upstream
        assert Path(path) == Path(context['repo']) / 'scripts/deploy-remote.py'
        return SimpleNamespace(ssh_options=ssh_options)

    monkeypatch.setattr(actions, 'load', load)
    transport = actions.graphato_module(context).deployment_transport()
    assert transport == ['ssh', *options, '-o', 'Port=2207', 'root@isolated-target']
    assert seen[0].identity == Path(context['work']) / 'identity'
    assert seen[0].known_hosts == Path(context['work']) / 'known_hosts'
    assert seen[0].host == 'isolated-target' and seen[0].user == 'root'
    assert not any(value.startswith(('ControlMaster=', 'ProxyCommand=')) for value in transport)


@pytest.mark.parametrize('port', [0, -1, 65536, 'not-a-port'])
def test_invalid_port_fails_before_any_transport_is_used(context, monkeypatch, port):
    context['profile']['graphato']['port'] = port
    monkeypatch.setattr(actions, 'load', lambda *args: SimpleNamespace(
        ssh_options=lambda args: pytest.fail('Must reject port before preparing SSH')))
    with pytest.raises(ValueError):
        actions.graphato_module(context).deployment_transport()


def test_upstream_host_key_validation_is_not_bypassed(context, monkeypatch):
    def reject(args):
        raise ValueError('SSH file missing')

    monkeypatch.setattr(actions, 'load', lambda *args: SimpleNamespace(ssh_options=reject))
    with pytest.raises(ValueError, match='SSH file missing'):
        actions.graphato_module(context).deployment_transport()


def test_failed_execution_can_use_upstream_cancellation_and_downloads(context, monkeypatch):
    calls = []
    upstream = SimpleNamespace(deployment_transport=lambda: ['ssh', '-o', 'ServerAliveCountMax=4', 'root@isolated-target'])

    def postdeploy(suite, commit, output, group):
        transport = upstream.deployment_transport()
        # These are distinct upstream operations. A lost initial connection must
        # not force the later commands through its dead control socket.
        for command in ('postdeploy', 'postdeploy-cancel', 'postdeploy-result', 'postdeploy-artifacts'):
            assert '-S' not in transport and 'ProxyCommand=false' not in transport
            calls.append(command)
        raise ValueError('Target-host verification exited with status 255')

    upstream.postdeploy = postdeploy
    monkeypatch.setattr(actions, 'graphato_module', lambda c: upstream)
    monkeypatch.setattr(actions.subprocess, 'Popen', lambda *a, **k: pytest.fail('No adapter-owned SSH master'))
    with pytest.raises(ValueError, match='status 255'):
        actions.graphato(context)
    assert calls == ['postdeploy', 'postdeploy-cancel', 'postdeploy-result', 'postdeploy-artifacts']
