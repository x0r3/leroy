"""Local admission must preserve the original probe and fence every mutation."""
import ast
import copy
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_capacity_agent as agent  # noqa: E402

probe_source = ast.parse((Path(__file__).resolve().parents[1] / 'scripts/nas_vm_file_capacity.py').read_text())
AGENT = next(ast.literal_eval(node.value) for node in probe_source.body if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id == 'AGENT' for target in node.targets))


@pytest.fixture
def simulation():
    class Probe:
        before = {'active_builds': [], 'jobs': {'native': {'number': 42}}}

        def __init__(self):
            self.requests, self.events, self.sleeps = [], [], []
            self.total = 0

        def production(self):
            return copy.deepcopy(self.before)

        def memory(self):
            return {'MemAvailable': 512 * 1024, 'SwapFree': 4096 * 1024}

        def control(self, action):
            self.requests.append(action)
            if action['action'] == 'allocate':
                self.total += action['mib']
                return {'kind': 'allocated', 'allocated_mib': self.total}
            if action['action'] == 'status':
                return {'kind': 'held', 'allocated_mib': self.total}
            return {'kind': 'stopped', 'allocated_mib': 0, 'all_page_markers_intact': True}

        def run(self, **overrides):
            return agent.sequence(self.before, overrides.get('production', self.production),
                                  overrides.get('memory', self.memory), overrides.get('control', self.control),
                                  lambda kind, value: self.events.append((kind, value)), sleep=self.sleeps.append)

    return Probe()


@pytest.fixture
def limits():
    return {'image': 'sha256:frozen', 'memory_bytes': 6 * 1024**3, 'memory_and_swap_bytes': 6 * 1024**3,
            'nano_cpus': 2 * 10**9, 'cgroup_swap_max': 0, 'program_sha256': hashlib.sha256(AGENT.encode()).hexdigest(),
            'hard_timeout_seconds': 1200, 'idle_timeout_seconds': 120}


def test_exact_original_allocation_hold_and_all_page_marker_contract(simulation):
    phases = simulation.run()
    assert [p['mib'] for p in simulation.requests if p['action'] == 'allocate'] == [512] * 11 + [256]
    assert len(phases) == 16 and phases[-1]['all_page_markers_intact']
    assert simulation.sleeps == [5] * 12 + [20] * 3
    assert [p['action'] for p in simulation.requests[-4:]] == ['status'] * 3 + ['stop']


@pytest.mark.parametrize('current', [
    {'active_builds': ['new'], 'jobs': {'native': {'number': 42}}},
    {'active_builds': [], 'jobs': {'native': {'number': 43}}},
])
def test_production_change_prevents_any_allocation(simulation, current):
    with pytest.raises(AssertionError, match='Production changed'):
        simulation.run(production=lambda: current)
    assert simulation.requests == [{'action': 'stop'}]


@pytest.mark.parametrize('memory', [
    {'MemAvailable': 256 * 1024 - 1, 'SwapFree': 4096 * 1024},
    {'MemAvailable': 512 * 1024, 'SwapFree': (2304 + 512 + 256) * 1024 - 1},
])
def test_unchanged_nas_floors_prevent_any_allocation(simulation, memory):
    with pytest.raises(AssertionError, match='reserve'):
        simulation.run(memory=lambda: memory)
    assert simulation.requests == [{'action': 'stop'}]


def test_lost_allocation_response_is_not_replayed(simulation):
    def control(action):
        value = simulation.control(action)
        if action['action'] == 'allocate':
            raise TimeoutError('The allocation may already have completed')
        return value

    with pytest.raises(TimeoutError):
        simulation.run(control=control)
    assert simulation.requests == [{'action': 'allocate', 'mib': 512}, {'action': 'stop'}]


def test_changed_production_during_hold_is_not_accepted(simulation):
    def production():
        return simulation.before if simulation.total < 5888 else {'active_builds': ['new'], 'jobs': {}}

    with pytest.raises(AssertionError):
        simulation.run(production=production)
    assert simulation.requests[-1] == {'action': 'stop'}
    assert not any(action['action'] == 'status' for action in simulation.requests)


@pytest.mark.parametrize('failure', ['wrong_amount', 'marker_loss', 'bad_status'])
def test_invalid_probe_response_cannot_publish_success(simulation, failure):
    def control(action):
        value = simulation.control(action)
        if failure == 'wrong_amount' and action['action'] == 'allocate':
            value['allocated_mib'] -= 256
        if failure == 'bad_status' and action['action'] == 'status':
            value['allocated_mib'] = 512
        if failure == 'marker_loss' and action['action'] == 'stop':
            value['all_page_markers_intact'] = False
        return value

    with pytest.raises(AssertionError):
        simulation.run(control=control)
    assert simulation.requests[-1] == {'action': 'stop'}


@pytest.mark.parametrize('field,value', [
    ('image', 'sha256:different'), ('memory_bytes', 5 * 1024**3), ('memory_and_swap_bytes', 7 * 1024**3),
    ('nano_cpus', 3 * 10**9), ('cgroup_swap_max', 1), ('program_sha256', 'changed'),
    ('hard_timeout_seconds', 1201), ('idle_timeout_seconds', 121),
])
def test_original_limits_and_probe_source_cannot_drift(limits, field, value):
    agent.require_limits(limits, 'sha256:frozen', hashlib.sha256(AGENT.encode()).hexdigest())
    with pytest.raises(AssertionError):
        agent.require_limits({**limits, field: value}, 'sha256:frozen', hashlib.sha256(AGENT.encode()).hexdigest())


def test_bridge_rejects_incomplete_receipt_and_changed_driver(simulation, limits):
    import nas_vm_capacity_local as bridge

    config = {'source_sha256': 'driver', 'image': 'sha256:frozen', 'guest_agent': AGENT}
    value = {'config_sha256': 'config', 'driver_source_sha256': 'driver', 'nas_local_admission': True,
             'qualified_synthetic_capacity': True, 'allocated_mib': 5888, 'hold_seconds': 60,
             'all_page_markers_intact': True, 'original_ci_dispatched': False, 'host_swap_changed': False,
             'limits': limits, 'phases': simulation.run(),
             'driver_resources': {'memory.low': str(32 * 1024**2), 'memory.max': str(128 * 1024**2),
                                  'memory.min': '0', 'memory.swap.max': '0', 'pids.max': '64', 'cpu.max': '50000 100000'}}
    bridge.validate_result(value, config, 'config')
    for key, changed in [('phases', value['phases'][:-1]), ('driver_source_sha256', 'wrong'),
                         ('hold_seconds', 59), ('all_page_markers_intact', False)]:
        with pytest.raises(AssertionError):
            bridge.validate_result({**value, key: changed}, config, 'config')


def test_bridge_lost_launch_reply_never_restarts_the_agent(monkeypatch, tmp_path, simulation, limits):
    import json
    import time

    import nas_vm_capacity_local as bridge

    monkeypatch.setattr(bridge.vm, 'ROOT', tmp_path)
    monkeypatch.setattr(bridge.vm, 'RESOURCE_PROFILE', bridge.vm.FILE_MEMORY_PROFILE)
    monkeypatch.setattr(bridge.vm, 'ROUND', tmp_path.name)
    monkeypatch.setattr(bridge.vm, '_GUEST_PIN', {'pinned': True})
    source = tmp_path / 'scripts/nas_capacity_agent.py'
    source.parent.mkdir()
    source.write_text('qualified driver')
    approval_path = tmp_path / 'approval.json'
    approval_path.write_text('{}')
    (tmp_path / 'leroy-memory-trace.json').write_text('{}')
    approval = {'absolute_deadline_epoch': time.time() + 5000, 'window': 'owned-window',
                'script_sha256': {'scripts/nas_resource_window_guard.py': 'guard'}}
    monkeypatch.setattr(bridge, 'approval_for', lambda *args: (approval_path, approval))
    monkeypatch.setattr(bridge, 'production_jobs', lambda: simulation.before)
    monkeypatch.setattr(bridge, 'production_jobs_program', lambda **kwargs: 'canonical read')
    scenario = tmp_path / 'test-results/nas-parity/followup/candidates/graphato' / bridge.vm.COMMIT / 'scenarios/root-private-existing-host/scenario.json'
    scenario.parent.mkdir(parents=True)
    scenario.write_text(json.dumps({'baseline_release': {'runtimeImageId': 'sha256:frozen'}}))
    calls = []

    def remote(program, **kwargs):
        calls.append(program)
        if len(calls) == 1:
            raise bridge.vm.SSHTransportUnavailable('Launch outcome unknown')
        config = json.loads((tmp_path / 'leroy-nas-capacity-config.json').read_text())
        intent = json.loads((tmp_path / 'leroy-nas-capacity-intent.json').read_text())
        value = {'config_sha256': intent['config_sha256'], 'driver_source_sha256': config['source_sha256'],
                 'nas_local_admission': True, 'qualified_synthetic_capacity': True, 'allocated_mib': 5888,
                 'hold_seconds': 60, 'all_page_markers_intact': True, 'original_ci_dispatched': False,
                 'host_swap_changed': False, 'limits': limits, 'phases': simulation.run(),
                 'driver_resources': {'memory.low': str(32 * 1024**2), 'memory.max': str(128 * 1024**2),
                                      'memory.min': '0', 'memory.swap.max': '0', 'pids.max': '64', 'cpu.max': '50000 100000'}}
        return json.dumps({'files': {'result.json': value}, 'unit_active_state': 'inactive'})

    monkeypatch.setattr(bridge.vm, 'remote', remote)
    result = bridge.qualify(tmp_path, 'leroy', guest_agent=AGENT, start_program='start once', control_program='control')
    assert result['qualified_synthetic_capacity']
    assert len(calls) == 2 and 'systemd-run' in calls[0] and 'systemd-run' not in calls[1]
    assert json.loads((tmp_path / 'leroy-nas-capacity-launch-unknown.json').read_text())['launch_repeated'] is False


def test_bridge_existing_intent_blocks_any_second_launch(monkeypatch, tmp_path):
    import nas_vm_capacity_local as bridge

    monkeypatch.setattr(bridge.vm, 'RESOURCE_PROFILE', bridge.vm.FILE_MEMORY_PROFILE)
    monkeypatch.setattr(bridge.vm, 'ROUND', tmp_path.name)
    (tmp_path / 'leroy-nas-capacity-intent.json').write_text('{}')
    monkeypatch.setattr(bridge.vm, 'remote', lambda *args, **kwargs: pytest.fail('No second launch'))
    with pytest.raises(AssertionError, match='never start another'):
        bridge.qualify(tmp_path, 'leroy', guest_agent=AGENT, start_program='start', control_program='control')


@pytest.mark.parametrize('stderr,expected', [
    (b'JSONDecodeError: Expecting value\n', ['JSONDecodeError']),
    (b'json.decoder.JSONDecodeError: Expecting value\n', ['JSONDecodeError']),
    (b'ConnectionRefusedError: [Errno 111] Connection refused\n', ['ConnectionRefusedError']),
    (b'TimeoutError: timed out\n', ['TimeoutError']),
    (b'Unclassified application data and tokens', []),
])
def test_guest_failure_facts_do_not_export_arbitrary_logs(stderr, expected):
    import json

    raw = b'secret-request-or-output'
    evidence = agent.guest_failure_metadata('allocate', 1, raw, stderr, 12.3456)
    assert evidence['returncode'] == 1 and evidence['elapsed_seconds'] == 12.346
    assert evidence['exception_types'] == expected
    assert evidence['stdout_sha256'] == hashlib.sha256(raw).hexdigest()
    assert evidence['stderr_sha256'] == hashlib.sha256(stderr).hexdigest()
    assert raw.decode() not in json.dumps(evidence) and stderr.decode().strip() not in json.dumps(evidence)
    assert evidence['outcome_unknown'] and not evidence['action_repeated'] and not evidence['raw_output_retained']


def test_lost_guest_response_keeps_a_timeout_distinct_from_nonzero_exit():
    evidence = agent.guest_failure_metadata('allocate', None, None, b'', 405, timed_out=True)
    error = agent.GuestOperationFailed(evidence)
    assert error.evidence == evidence and evidence['returncode'] is None and evidence['timed_out']
    assert evidence['outcome_unknown'] and not evidence['action_repeated']


def test_ssh_diagnostic_does_not_imply_no_allocation_or_authentication_success():
    evidence = agent.guest_failure_metadata('allocate', 255, b'', b'Connection reset by peer\nprivate-unknown-data', 10)
    assert evidence['transport_diagnostics'] == ['Connection reset']
    assert evidence['returncode'] == 255 and evidence['outcome_unknown'] and not evidence['action_repeated']
    assert 'private-unknown-data' not in str(evidence)


def test_failure_metadata_survives_cleanup_without_replaying_allocation(simulation):
    evidence = agent.guest_failure_metadata('allocate', 1, b'', b'JSONDecodeError: empty response', 42)

    def control(action):
        if action['action'] == 'allocate':
            simulation.requests.append(action)
            raise agent.GuestOperationFailed(evidence)
        return simulation.control(action)

    with pytest.raises(agent.GuestOperationFailed) as caught:
        simulation.run(control=control)
    assert caught.value.evidence == evidence
    assert simulation.requests == [{'action': 'allocate', 'mib': 512}, {'action': 'stop'}]


def test_failure_docker_events_are_pinned_and_omit_arbitrary_attributes(monkeypatch, capsys):
    import json
    import time

    cid = 'a' * 64
    events = [{'Type': 'container', 'Action': action, 'Actor': {'ID': cid, 'Attributes':
               {'exitCode': '137', 'image': 'private-image', 'unrelated': 'secret'}}, 'timeNano': 42}
              for action in ('create', 'oom', 'die', 'destroy')]
    calls = []

    def query(command, *, timeout):
        calls.append((command, timeout))
        return '\n'.join(json.dumps(row) for row in events).encode()

    monkeypatch.setattr(agent.subprocess, 'check_output', query)
    exec(compile(agent.PROBE_EXIT_PROGRAM, '<diagnostic-read>', 'exec'), {'CID': cid, 'SINCE': time.time() - 10})
    value = json.loads(capsys.readouterr().out)
    assert [row['action'] for row in value['events']] == ['oom', 'die', 'destroy']
    assert value['events'][1]['exitCode'] == 137
    assert 'secret' not in str(value) and 'private-image' not in str(value)
    assert calls[0][0][:2] == ['docker', 'events'] and 'container=' + cid in calls[0][0]
    assert calls[0][1] == 10 and value['read_only'] and not value['absence_of_events_proves_no_failure']


def test_failure_docker_events_from_another_container_are_rejected(monkeypatch):
    import json
    import time

    row = {'Type': 'container', 'Action': 'die', 'Actor': {'ID': 'b' * 64}}
    monkeypatch.setattr(agent.subprocess, 'check_output', lambda *args, **kwargs: json.dumps(row).encode())
    with pytest.raises(AssertionError):
        exec(compile(agent.PROBE_EXIT_PROGRAM, '<diagnostic-read>', 'exec'), {'CID': 'a' * 64, 'SINCE': time.time() - 10})


@pytest.mark.parametrize('cid,since', [('other', 0), ('a' * 64, 0)])
def test_invalid_or_stale_probe_reference_prevents_any_docker_query(monkeypatch, cid, since):
    monkeypatch.setattr(agent.subprocess, 'check_output', lambda *args, **kwargs: pytest.fail('No Docker call'))
    with pytest.raises(AssertionError):
        exec(compile(agent.PROBE_EXIT_PROGRAM, '<diagnostic-read>', 'exec'), {'CID': cid, 'SINCE': since})


def test_slow_admission_keeps_probe_active_without_adding_qualified_holds(simulation):
    import threading

    reached = threading.Event()
    events = []

    def status():
        reached.set()
        return {'kind': 'held', 'allocated_mib': 0}

    keeper = agent.ProbeKeepalive(status, lambda *args: events.append(args), interval=0.001, join_timeout=2)
    keeper.start()
    try:
        def admission():
            assert reached.wait(2), 'Read-only status must progress independently of slow admission'
            return simulation.production()

        phases = simulation.run(production=admission)
    finally:
        keeper.stop()
    keeper.check()
    assert keeper.count > 0 and not keeper.thread.is_alive()
    assert all(row[1]['counts_as_hold_or_marker_check'] is False for row in events)
    assert len(phases) == 16 and sum(p['kind'] == 'held' for p in phases) == 3
    assert [r['mib'] for r in simulation.requests if r['action'] == 'allocate'] == [512] * 11 + [256]


@pytest.mark.parametrize('response', [
    {'kind': 'allocated', 'allocated_mib': 512}, {'kind': 'stopped', 'allocated_mib': 0},
    {'kind': 'held', 'allocated_mib': True}, {'kind': 'held', 'allocated_mib': -256},
])
def test_invalid_keepalive_latches_failure_and_prevents_next_allocation(simulation, response):
    keeper = agent.ProbeKeepalive(lambda: response, lambda *args: None, interval=0.001, join_timeout=2)
    keeper.start()
    assert keeper.stopping.wait(2)
    keeper.stop()

    def control(action):
        if action['action'] != 'stop':
            keeper.check()
        return simulation.control(action)

    with pytest.raises(RuntimeError, match='no further allocation'):
        simulation.run(control=control)
    assert simulation.requests == [{'action': 'stop'}] and keeper.count == 0


def test_pending_keepalive_cannot_certify_stopped_observer():
    import threading

    started, release = threading.Event(), threading.Event()

    def status():
        started.set()
        assert release.wait(2)
        return {'kind': 'held', 'allocated_mib': 0}

    keeper = agent.ProbeKeepalive(status, lambda *args: None, interval=0.001, join_timeout=0.01)
    keeper.start()
    assert started.wait(2)
    try:
        with pytest.raises(AssertionError, match='read remains pending'):
            keeper.stop()
    finally:
        release.set()
        keeper.thread.join(timeout=2)
    assert not keeper.thread.is_alive()


@pytest.mark.parametrize('mode,uid,links', [(0o140644, 0, 1), (0o140600, 1000, 1), (0o140600, 0, 2), (0o100600, 0, 1)])
def test_keepalive_rejects_unowned_nonprivate_or_non_socket_master(mode, uid, links):
    from types import SimpleNamespace

    class Socket:
        def lstat(self):
            return SimpleNamespace(st_mode=mode, st_uid=uid, st_nlink=links)

        def resolve(self, **kwargs):
            return self

    with pytest.raises(AssertionError):
        agent.existing_mux_command(['nsenter', '-t', '123', '-n', 'ssh'], Socket())


def test_keepalive_uses_only_existing_master_and_disables_new_connection_fallback():
    from types import SimpleNamespace

    class Socket:
        def lstat(self):
            return SimpleNamespace(st_mode=0o140600, st_uid=0, st_nlink=1)

        def resolve(self, **kwargs):
            return self

        def __str__(self):
            return '/owned/private/guest.sock'

    path = Socket()
    original = ['nsenter', '-t', '123', '-n', 'ssh', '-T', '-o', 'ControlMaster=auto',
                '-o', 'ControlPath=' + str(path), 'user@127.0.0.1', 'sudo python3 -B -']
    command = agent.existing_mux_command(original, path)
    assert command[0] == 'ssh' and 'nsenter' not in command
    assert 'ControlMaster=no' in command and 'ControlMaster=auto' not in command
    assert command[-4:] == ['-o', 'ProxyCommand=false', 'user@127.0.0.1', 'sudo python3 -B -']
