"""Recovery must preserve unrelated services and reject replacement targets."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def guard(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, 'fcntl', SimpleNamespace())
    spec = importlib.util.spec_from_file_location('resource_guard', Path(__file__).resolve().parents[1] / 'scripts/nas_resource_window_guard.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.DATA = tmp_path
    # The production journal uses Linux directory fsync. These tests exercise
    # recovery decisions on Windows; the NAS already verified the real journal.
    monkeypatch.setattr(module, 'save', lambda name, value: (tmp_path / name).write_text(json.dumps(value)))
    return module


def test_restore_starts_only_services_stopped_by_window(guard, monkeypatch):
    monkeypatch.setattr(guard, 'stop_owned_vm', lambda state: None)
    state = {'phase': 'paused', 'events': [], 'containers': [
        {'name': 'paperless', 'id': 'a' * 64, 'phase': 'stopped'},
        {'name': 'sonarr', 'id': 'b' * 64, 'phase': 'eligible'},
    ]}
    guard.save('state.json', state)
    commands = []
    monkeypatch.setattr(guard, 'end_test_load', lambda s: None)
    monkeypatch.setattr(guard, 'reviewed', lambda row: {'State': {'Running': bool(commands)}, 'RestartCount': 0})
    monkeypatch.setattr(guard, 'command', lambda args, **kw: commands.append(args))
    result = guard.restore('completed')
    assert commands == [['docker', 'start', 'a' * 64]]
    assert result['phase'] == 'restored'
    assert result['containers'][1]['phase'] == 'eligible'
    guard.restore('repeated_request')
    assert len(commands) == 1


@pytest.mark.parametrize('phase', ['rust-leroy', 'rust-jenkins', 'release-leroy', 'release-jenkins'])
def test_open_grant_execution_registry_retains_exact_approved_deadline(guard, monkeypatch, tmp_path, phase):
    name = 'resource-window-acceptance-20261017-v-' + phase
    assert name in guard.DAY_WINDOWS, 'Execution entry point must admit the policy-approved window'
    data = tmp_path / name
    data.mkdir()
    monkeypatch.setattr(guard, 'DATA', data)
    monkeypatch.setattr(guard.time, 'time', lambda: 1000)
    rows = [{'name': n, 'id': format(i + 1, '064x')} for i, n in enumerate(sorted(guard.ALLOWED))]
    plan = {'user_approved': True, 'maximum_window_seconds': 14400,
            'comparison_rounds': guard.OPEN_WINDOWS[name], 'source_commit': guard.COMMIT,
            'graceful_stop_seconds': 120, 'absolute_deadline_epoch': 10000,
            'explicit_user_request': 'Das Wartungsfenster ist nun unbegrenzt offen. Fahre fort wie vorgeschlagen',
            'continuation_authorization': {'open_ended': True, 'closed_windows_extended': False,
                                          'authorization_sha256': 'a' * 64},
            'production_counters': {}, 'containers': rows}
    (data / 'plan.json').write_text(json.dumps(plan))
    monkeypatch.setattr(guard, 'production_counters', lambda state: {})

    def inspect(identity, prefix=None):
        if identity in {'leroy-nas-release-target-vm', 'jenkins-parity'}:
            return {'State': {'Running': False}, 'Id': identity}
        if identity == 'leroy-nas-parity-docker-1':
            return {'Id': 'outer', 'Config': {'Labels': {'com.docker.compose.project': 'leroy-nas-parity'}}}
        if identity == 'jenkins':
            return {'Mounts': [{'Source': '/owned/native', 'Destination': '/var/jenkins_home'}]}
        row, = [r for r in rows if r['id'] == identity]
        return {'Id': identity, 'Name': '/' + row['name'], 'State': {'Running': True},
                'Image': 'same', 'Config': {}, 'HostConfig': {}, 'Mounts': []}

    monkeypatch.setattr(guard, 'inspect', inspect)
    state = guard.prepare()
    assert state['absolute_deadline_epoch'] == 10000
    assert state['restore_margin_seconds'] == 900 and state['started_at'] is None


def test_recovery_waits_for_test_load_to_stop_before_starting_apps(guard, monkeypatch):
    state = {'phase': 'paused', 'events': [], 'containers': [
        {'name': 'paperless', 'id': 'a' * 64, 'phase': 'stopped'}]}
    guard.save('state.json', state)

    def pending(_):
        raise TimeoutError('VM still running')

    monkeypatch.setattr(guard, 'stop_owned_vm', pending)
    monkeypatch.setattr(guard, 'reviewed', lambda row: pytest.fail('Do not restore apps over active test load'))
    result = guard.restore('test')
    assert result['phase'] == 'restore_error'
    assert result['containers'][0]['phase'] == 'stopped'
    assert 'finished_at' not in result


def test_direct_vm_stop_rejects_a_reused_pid(guard, monkeypatch):
    state = {'events': [], 'owned_vm_process': {'pid': 123, 'identity': {'start_ticks': 'old'}}}
    monkeypatch.setattr(guard, 'process_identity', lambda pid: {'start_ticks': 'new'})
    monkeypatch.setattr(guard.os, 'kill', lambda *args: pytest.fail('Never signal a reused PID'))
    with pytest.raises(AssertionError, match='reused or changed'):
        guard.direct_stop_owned_vm(state)


@pytest.mark.parametrize('api_available', [True, False])
def test_identity_refresh_tolerates_boot_gap_but_not_daemon_failure(guard, monkeypatch, api_available):
    state = {}

    def absent(*args):
        raise RuntimeError('Container absent or API unavailable')

    def listing(args):
        assert args == ['docker', 'ps', '-aq', '--no-trunc', '--filter', 'name=^/leroy-nas-release-target-vm$']
        if not api_available:
            raise RuntimeError('API unavailable')
        return ''

    monkeypatch.setattr(guard, 'inspect', absent)
    monkeypatch.setattr(guard, 'command', listing)
    if api_available:
        assert guard.remember_owned_vm(state) is False
    else:
        with pytest.raises(RuntimeError, match='API unavailable'):
            guard.remember_owned_vm(state)
    assert state == {}


def test_verified_vm_gets_grace_before_forced_shutdown(guard, monkeypatch):
    identity = {'start_ticks': 'original', 'cgroup': 'owned', 'command_sha256': 'sha'}
    state = {'events': [], 'owned_vm_process': {'pid': 123, 'identity': identity}}
    now = [1000]
    calls = []
    monkeypatch.setattr(guard.signal, 'SIGKILL', 9, raising=False)
    monkeypatch.setattr(guard, 'process_identity', lambda pid: identity)
    monkeypatch.setattr(guard.time, 'time', lambda: now[0])
    monkeypatch.setattr(guard.os, 'kill', lambda pid, sig: calls.append((pid, sig)))
    assert not guard.direct_stop_owned_vm(state)
    now[0] += 209
    assert not guard.direct_stop_owned_vm(state)
    assert calls == [(123, guard.signal.SIGTERM)]
    now[0] += 1
    assert not guard.direct_stop_owned_vm(state)
    assert calls[-1] == (123, guard.signal.SIGKILL)
    monkeypatch.setattr(guard, 'process_identity', lambda pid: None)
    assert guard.direct_stop_owned_vm(state)


@pytest.mark.parametrize('forced', [False, True])
def test_shutdown_signal_is_not_blocked_by_failed_journal_sync(guard, monkeypatch, forced):
    identity = {'start_ticks': 'original', 'cgroup': 'owned', 'command_sha256': 'sha'}
    state = {'events': [], 'owned_vm_process': {'pid': 123, 'identity': identity}}
    if forced:
        state['owned_vm_stop_requested_at'] = 1000
    calls = []
    monkeypatch.setattr(guard.signal, 'SIGKILL', 9, raising=False)
    monkeypatch.setattr(guard, 'process_identity', lambda pid: identity)
    monkeypatch.setattr(guard.time, 'time', lambda: 1210)
    monkeypatch.setattr(guard.os, 'kill', lambda pid, sig: calls.append((pid, sig)))

    def failed_sync(*args):
        raise TimeoutError('journal disk unavailable')

    monkeypatch.setattr(guard, 'save', failed_sync)
    with pytest.raises(TimeoutError):
        guard.direct_stop_owned_vm(state)
    assert calls == [(123, guard.signal.SIGKILL if forced else guard.signal.SIGTERM)]


def test_failed_signal_does_not_start_the_grace_clock(guard, monkeypatch):
    identity = {'start_ticks': 'original'}
    state = {'events': [], 'owned_vm_process': {'pid': 123, 'identity': identity}}
    monkeypatch.setattr(guard, 'process_identity', lambda pid: identity)

    def rejected(*args):
        raise PermissionError('signal not accepted')

    monkeypatch.setattr(guard.os, 'kill', rejected)
    with pytest.raises(PermissionError):
        guard.direct_stop_owned_vm(state)
    assert 'owned_vm_stop_requested_at' not in state and not state['events']


def test_restore_queues_verified_stop_before_its_first_journal_write(guard, monkeypatch):
    identity = {'start_ticks': 'original'}
    state = {'phase': 'paused', 'events': [], 'containers': [],
             'owned_vm_process': {'pid': 123, 'identity': identity}}
    guard.save('state.json', state)
    calls = []
    monkeypatch.setattr(guard, 'process_identity', lambda pid: identity)
    monkeypatch.setattr(guard.os, 'kill', lambda pid, sig: calls.append((pid, sig)))
    def unavailable(*args):
        raise RuntimeError('Docker unavailable')

    monkeypatch.setattr(guard, 'inspect', unavailable)

    def failed_sync(*args):
        raise TimeoutError('journal unavailable')

    monkeypatch.setattr(guard, 'save', failed_sync)
    with pytest.raises(TimeoutError):
        guard.restore('completed')
    assert calls == [(123, guard.signal.SIGTERM)]


@pytest.mark.parametrize('available,swap,expected', [
    (128 * 1024, 2304 * 1024, None),
    (128 * 1024 - 1, 2304 * 1024, 'host_available_reserve'),
    (128 * 1024, 2304 * 1024 - 1, 'host_swap_reserve'),
])
def test_independent_host_guard_preserves_existing_reserve_floors(guard, available, swap, expected):
    result = guard.reserve_violation(f'MemAvailable: {available} kB\nSwapFree: {swap} kB\n')
    assert (result['reason'] if result else None) == expected


def test_critical_host_reserve_bypasses_hung_docker_but_checks_pid_each_signal(guard, monkeypatch):
    identity = {'start_ticks': 'original', 'cgroup': 'owned', 'command_sha256': 'sha'}
    state = {'events': [], 'host_reserve_stop': {'reason': 'host_swap_reserve'},
             'owned_vm_process': {'pid': 123, 'identity': identity}}
    now = [1000]
    signals = []
    monkeypatch.setattr(guard.signal, 'SIGKILL', 9, raising=False)
    monkeypatch.setattr(guard, 'process_identity', lambda pid: identity)
    monkeypatch.setattr(guard.time, 'time', lambda: now[0])
    monkeypatch.setattr(guard.os, 'kill', lambda pid, sig: signals.append((pid, sig)))
    monkeypatch.setattr(guard, 'inspect', lambda *a: pytest.fail('Do not wait on Docker during reserve exhaustion'))
    with pytest.raises(RuntimeError, match='pending'):
        guard.stop_owned_vm(state)
    now[0] += 9
    with pytest.raises(RuntimeError, match='pending'):
        guard.stop_owned_vm(state)
    assert signals == [(123, guard.signal.SIGTERM)]
    now[0] += 1
    with pytest.raises(RuntimeError, match='pending'):
        guard.stop_owned_vm(state)
    assert signals[-1] == (123, guard.signal.SIGKILL)
    monkeypatch.setattr(guard, 'process_identity', lambda pid: {'start_ticks': 'reused'})
    with pytest.raises(AssertionError, match='reused or changed'):
        guard.stop_owned_vm(state)


def test_watchdog_checks_host_reserve_without_waiting_for_production_docker_queries(guard, monkeypatch):
    identity = {'start_ticks': 'verified', 'cgroup': 'owned', 'command_sha256': 'sha'}
    state = {'phase': 'paused', 'started_at': 1, 'deadline': 9999999999,
             'owned_vm_process': {'pid': 123, 'identity': identity}, 'events': []}
    guard.save('state.json', state)
    observation = {'reason': 'host_swap_reserve', 'available_kib': 512000, 'swap_free_kib': 2359295}
    monkeypatch.setattr(guard, 'fcntl', SimpleNamespace(flock=lambda *a: None, LOCK_EX=2))
    monkeypatch.setattr(guard.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(guard, 'process_identity', lambda pid: identity)
    monkeypatch.setattr(guard, 'Path', lambda path: SimpleNamespace(read_text=lambda: 'host meminfo'))
    monkeypatch.setattr(guard, 'reserve_violation', lambda text: observation)
    monkeypatch.setattr(guard, 'production_counters', lambda state: pytest.fail('Do not await production I/O on reserve exhaustion'))
    calls = []
    signals = []
    monkeypatch.setattr(guard.os, 'kill', lambda pid, sig: signals.append((pid, sig)))

    def restore(reason):
        assert guard.read()['host_reserve_stop'] == observation
        calls.append(reason)
        return {'phase': 'restored'}

    monkeypatch.setattr(guard, 'restore', restore)
    assert guard.watch()['phase'] == 'restored'
    assert calls == ['host_swap_reserve']
    assert signals == [(123, guard.signal.SIGTERM)]


def test_critical_reserve_signal_precedes_a_blocked_watchdog_journal(guard, monkeypatch):
    identity = {'start_ticks': 'original'}
    state = {'phase': 'paused', 'started_at': 1, 'deadline': 9999999999,
             'owned_vm_process': {'pid': 123, 'identity': identity}, 'events': []}
    guard.save('state.json', state)
    monkeypatch.setattr(guard, 'fcntl', SimpleNamespace(flock=lambda *a: None, LOCK_EX=2))
    monkeypatch.setattr(guard.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(guard, 'process_identity', lambda pid: identity)
    monkeypatch.setattr(guard, 'Path', lambda path: SimpleNamespace(read_text=lambda: 'host meminfo'))
    monkeypatch.setattr(guard, 'reserve_violation', lambda text: {'reason': 'host_swap_reserve'})
    monkeypatch.setattr(guard, 'production_counters', lambda *a: pytest.fail('No production Docker query'))
    calls = []
    monkeypatch.setattr(guard.os, 'kill', lambda pid, sig: calls.append((pid, sig)))

    def failed_sync(*args):
        raise TimeoutError('NAS journal unavailable')

    monkeypatch.setattr(guard, 'save', failed_sync)
    with pytest.raises(TimeoutError):
        guard.watch()
    assert calls == [(123, guard.signal.SIGTERM)]


def test_configuration_change_prevents_unreviewed_restart(guard, monkeypatch):
    info = {'Id': 'a' * 64, 'Name': '/paperless', 'Image': 'image', 'Config': {}, 'HostConfig': {}, 'Mounts': []}
    row = {'name': 'paperless', 'id': info['Id'], 'phase': 'stopped', 'configuration_sha256': guard.fingerprint(info)}
    info['HostConfig']['Memory'] = 123
    monkeypatch.setattr(guard, 'inspect', lambda identity: info)
    with pytest.raises(AssertionError):
        guard.reviewed(row)


def test_mount_order_does_not_change_reviewed_configuration(guard):
    info = {'Id': 'a' * 64, 'Name': '/paperless', 'Image': 'image', 'Config': {}, 'HostConfig': {},
            'Mounts': [{'Source': '/one', 'Destination': '/a'}, {'Source': '/two', 'Destination': '/b'}]}
    expected = guard.fingerprint(info)
    info['Mounts'].reverse()
    assert guard.fingerprint(info) == expected


def test_capacity_window_requires_its_own_explicit_approval_and_deadline(guard):
    plan = {'maximum_window_seconds': 3600, 'user_approved': True,
            'comparison_round': guard.CAPACITY_ROUND, 'synthetic_only': True, 'original_ci_dispatched': False}
    assert guard.window_policy(plan, guard.CAPACITY_WINDOW) == (3600, [guard.CAPACITY_ROUND], 900)
    for field, value in [('user_approved', False), ('maximum_window_seconds', 14400),
                         ('comparison_round', guard.RECONCILE_RELEASE_ROUND),
                         ('synthetic_only', False), ('original_ci_dispatched', True)]:
        with pytest.raises(AssertionError):
            guard.window_policy({**plan, field: value}, guard.CAPACITY_WINDOW)


def test_night_policy_requires_new_scope_and_a_bounded_absolute_end(guard, monkeypatch):
    monkeypatch.setattr(guard.time, 'time', lambda: 1000)
    plan = {'maximum_window_seconds': 36000, 'user_approved': True,
            'comparison_rounds': guard.NIGHT_ROUNDS, 'source_commit': guard.COMMIT,
            'explicit_user_request': 'Das Fenster wird die ganze Nacht laufen', 'absolute_deadline_epoch': 10000}
    assert guard.window_policy(plan, guard.NIGHT_WINDOW) == (36000, guard.NIGHT_ROUNDS, 900)
    for field, value in [('user_approved', False), ('comparison_rounds', [guard.CAPACITY_ROUND]),
                         ('absolute_deadline_epoch', 2000), ('absolute_deadline_epoch', 50000),
                         ('source_commit', 'other'), ('explicit_user_request', '')]:
        with pytest.raises(AssertionError):
            guard.window_policy({**plan, field: value}, guard.NIGHT_WINDOW)


@pytest.mark.parametrize('name', ['resource-window-day-20261015-rust-leroy',
                                  'resource-window-day-20261015-b-rust-leroy',
                                  'resource-window-day-20261015-c-rust-leroy',
                                  'resource-window-day-20261015-d-rust-leroy',
                                  'resource-window-day-20261015-i-rust-leroy',
                                  'resource-window-day-20261015-i-rust-jenkins',
                                  'resource-window-day-20261015-i-release-leroy',
                                  'resource-window-day-20261015-i-release-jenkins'])
def test_day_guard_cannot_extend_past_midnight_or_reuse_night_namespace(guard, monkeypatch, name):
    monkeypatch.setattr(guard.time, 'time', lambda: guard.DAY_END - 10000)
    rounds = guard.DAY_WINDOWS[name]
    plan = {'maximum_window_seconds': 14400, 'user_approved': True, 'comparison_rounds': rounds,
            'source_commit': guard.COMMIT, 'explicit_user_request': 'den ganzen Tag',
            'absolute_deadline_epoch': guard.DAY_END}
    assert guard.window_policy(plan, name) == (14400, rounds, 900)
    with pytest.raises(AssertionError):
        guard.window_policy({**plan, 'absolute_deadline_epoch': guard.DAY_END + 1}, name)
    with pytest.raises(AssertionError):
        guard.window_policy(plan, guard.ORIGINAL_NIGHT_WINDOW)


def test_next_day_grant_only_applies_to_its_new_namespace(guard, monkeypatch):
    monkeypatch.setattr(guard.time, 'time', lambda: guard.DAY_END - 1000)
    name = 'resource-window-day-20261015-m-rust-leroy'
    plan = {'maximum_window_seconds': 14400, 'user_approved': True,
            'comparison_rounds': guard.DAY_WINDOWS[name], 'source_commit': guard.COMMIT,
            'explicit_user_request': 'Zwischenhinweis, dein Arbeitsfenster ist noch für den gesamten morgigen Tag freigegeben',
            'absolute_deadline_epoch': guard.DAY_END + 10000}
    assert guard.window_policy(plan, name) == (14400, guard.DAY_WINDOWS[name], 900)
    for change in ({'explicit_user_request': 'den ganzen Tag'}, {'absolute_deadline_epoch': guard.CONTINUATION_END + 1},
                   {'absolute_deadline_epoch': guard.DAY_END + 14000}):
        with pytest.raises(AssertionError):
            guard.window_policy({**plan, **change}, name)
    old = 'resource-window-day-20261015-l-rust-leroy'
    with pytest.raises(AssertionError):
        guard.window_policy({**plan, 'comparison_rounds': guard.DAY_WINDOWS[old]}, old)


def test_original_night_cannot_inherit_capacity_scope(guard, monkeypatch):
    monkeypatch.setattr(guard.time, 'time', lambda: 1000)
    plan = {'maximum_window_seconds': 36000, 'user_approved': True,
            'comparison_rounds': guard.ORIGINAL_NIGHT_ROUNDS, 'source_commit': guard.COMMIT,
            'explicit_user_request': 'Das Fenster wird die ganze Nacht laufen', 'absolute_deadline_epoch': 10000}
    assert guard.window_policy(plan, guard.ORIGINAL_NIGHT_WINDOW) == (36000, guard.ORIGINAL_NIGHT_ROUNDS, 900)
    with pytest.raises(AssertionError):
        guard.window_policy({**plan, 'comparison_rounds': guard.NIGHT_ROUNDS}, guard.ORIGINAL_NIGHT_WINDOW)


def test_night_pause_cannot_extend_the_fixed_morning_deadline(guard, monkeypatch):
    state = {'phase': 'prepared', 'started_at': None, 'deadline': None,
             'absolute_deadline_epoch': 10000, 'maximum_window_seconds': 36000,
             'production_counters': {}, 'containers': []}
    guard.save('state.json', state)
    monkeypatch.setattr(guard, 'production_counters', lambda s: {})
    monkeypatch.setattr(guard.time, 'time', lambda: 1000)
    first = guard.pause()
    assert first['deadline'] == 10000
    first['phase'] = 'prepared'
    guard.save('state.json', first)
    monkeypatch.setattr(guard.time, 'time', lambda: 3000)
    assert guard.pause()['deadline'] == 10000
    with pytest.raises(AssertionError):
        guard.reopen()


def test_expired_prepared_night_window_does_not_pause_services(guard, monkeypatch):
    guard.save('state.json', {'phase': 'prepared', 'started_at': None, 'deadline': None,
                             'absolute_deadline_epoch': 3000, 'maximum_window_seconds': 36000,
                             'production_counters': {}, 'containers': []})
    monkeypatch.setattr(guard, 'production_counters', lambda s: {})
    monkeypatch.setattr(guard.time, 'time', lambda: 2000)
    with pytest.raises(AssertionError):
        guard.pause()
    assert guard.read()['started_at'] is None


def test_deadline_cannot_stop_an_unrelated_vm(guard, monkeypatch):
    calls = []
    monkeypatch.setattr(guard, 'inspect', lambda identity: {
        'Id': 'a' * 64, 'State': {'Running': True},
        'Config': {'Labels': {'io.leroy.nas-release-target': guard.COMMIT, 'io.leroy.comparison': 'other-owner-round'}},
    })
    monkeypatch.setattr(guard, 'command', lambda args, **kw: calls.append(args))
    with pytest.raises(AssertionError):
        guard.stop_owned_vm({})
    assert calls == []


def test_failed_test_shutdown_does_not_prevent_service_recovery(guard, monkeypatch):
    monkeypatch.setattr(guard, 'stop_owned_vm', lambda state: None)
    state = {'phase': 'paused', 'events': [], 'containers': [
        {'name': 'plex', 'id': 'a' * 64, 'phase': 'stopped'},
    ]}
    guard.save('state.json', state)
    commands = []
    def shutdown(state):
        raise TimeoutError('private diagnostic failure')
    monkeypatch.setattr(guard, 'end_test_load', shutdown)
    monkeypatch.setattr(guard, 'reviewed', lambda row: {'State': {'Running': bool(commands)}, 'RestartCount': 0})
    monkeypatch.setattr(guard, 'command', lambda args, **kw: commands.append(args))
    result = guard.restore('deadline')
    assert commands == [['docker', 'start', 'a' * 64]]
    assert result['events'][-1]['type'] == 'TimeoutError'
    assert 'private diagnostic failure' not in json.dumps(result)


def test_followup_preserves_original_absolute_deadline(guard, monkeypatch):
    state = {'phase': 'restored', 'events': [], 'started_at': 1000, 'deadline': 8200,
             'outer_daemon_id': 'outer', 'private_jenkins_id': 'private', 'production_counters': {},
             'containers': [{'name': 'paperless', 'id': 'a' * 64, 'phase': 'restored'}]}
    guard.save('state.json', state)
    monkeypatch.setattr(guard.time, 'time', lambda: 2000)
    monkeypatch.setattr(guard, 'production_counters', lambda s: {})
    monkeypatch.setattr(guard, 'inspect', lambda *args: {'State': {'Running': False}})
    monkeypatch.setattr(guard, 'reviewed', lambda r: {'State': {'Running': True, 'Health': {'Status': 'healthy'}}})
    result = guard.reopen()
    assert result['deadline'] == 8200 and result['started_at'] == 1000
    assert result['attempt'] == 2
    assert (guard.DATA / 'completed-attempt-1.json').is_file()


def test_followup_is_refused_without_original_remaining_budget(guard, monkeypatch):
    guard.save('state.json', {'phase': 'restored', 'events': [], 'started_at': 1000, 'deadline': 8200})
    monkeypatch.setattr(guard.time, 'time', lambda: 7000)
    with pytest.raises(AssertionError, match='another two hours'):
        guard.reopen()


def test_full_release_pause_uses_one_absolute_four_hour_deadline(guard, monkeypatch):
    state = {'phase': 'prepared', 'events': [], 'started_at': None, 'deadline': None,
             'maximum_window_seconds': 14400, 'production_counters': {}, 'containers': []}
    guard.save('state.json', state)
    monkeypatch.setattr(guard.time, 'time', lambda: 1000)
    monkeypatch.setattr(guard, 'production_counters', lambda s: {})
    result = guard.pause()
    assert result['started_at'] == 1000 and result['deadline'] == 15400
    result['phase'] = 'prepared'
    guard.save('state.json', result)
    monkeypatch.setattr(guard.time, 'time', lambda: 2000)
    assert guard.pause()['deadline'] == 15400


def test_four_hour_window_cannot_reopen_as_old_two_hour_followup(guard):
    guard.save('state.json', {'phase': 'restored', 'maximum_window_seconds': 14400})
    with pytest.raises(AssertionError, match='separate journals'):
        guard.reopen()


def test_full_release_shutdown_is_scoped_to_journal_round(guard, monkeypatch):
    monkeypatch.setattr(guard, 'inspect', lambda *args: {
        'Id': 'a' * 64, 'Name': '/jenkins-parity', 'State': {'Running': True},
        'Config': {'Labels': {'io.leroy.nas-release-target': guard.COMMIT,
                              'io.leroy.comparison': 'resource-window-clippy-leroy-20261013'}},
    })
    with pytest.raises(AssertionError):
        guard.stop_owned_vm({'comparison_rounds': [guard.FULL_RELEASE_ROUND]})


def test_new_window_cannot_inherit_old_approval_or_comparison_scope(guard, monkeypatch, tmp_path):
    directory = tmp_path / 'resource-window-reconcile8g-leroy-20261014'
    directory.mkdir()
    guard.DATA = directory
    plan = {'containers': [{'name': name} for name in guard.ALLOWED], 'maximum_window_seconds': 14400,
            'user_approved': False, 'comparison_round': guard.RECONCILE_RELEASE_ROUND}
    (directory / 'plan.json').write_text(json.dumps(plan))
    monkeypatch.setattr(guard, 'inspect', lambda *args: pytest.fail('No NAS access before approval'))
    with pytest.raises(AssertionError):
        guard.prepare()
    plan.update(user_approved=True, comparison_round=guard.FULL_RELEASE_ROUND)
    (directory / 'plan.json').write_text(json.dumps(plan))
    with pytest.raises(AssertionError):
        guard.prepare()


def test_new_window_driver_refuses_dispatch_without_fresh_approval(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    import run_nas_full_release_window as driver

    monkeypatch.setattr(driver, 'ROUND', driver.RECONCILE_ROUND)
    monkeypatch.setattr(driver, 'FOLLOWUP', tmp_path)
    monkeypatch.setattr(driver, 'prepare', lambda *args: pytest.fail('No preparation without new approval'))
    with pytest.raises(AssertionError, match='previous windows are closed'):
        driver.run_window('leroy')
    assert not any(tmp_path.iterdir())


@pytest.fixture
def rust_gate(monkeypatch, tmp_path):
    import io
    import tarfile

    # The retained Jenkins archive layout exceeds the Windows MAX_PATH limit
    # beneath pytest's descriptive per-test directory.
    if sys.platform == 'win32':
        tmp_path = Path('\\\\?\\' + str(tmp_path))
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    import compare_frozen_postdeploy_group as evidence
    import run_nas_full_release_window as driver

    monkeypatch.setattr(evidence, 'ROOT', tmp_path)
    case = tmp_path / 'case'
    case.mkdir()
    commit = driver.vm.COMMIT
    log = '\n'.join(json.dumps(row) for row in [
        {'type': 'suite', 'event': 'started', 'test_count': 2},
        {'type': 'test', 'event': 'ok', 'name': 'suite::first'},
        {'type': 'test', 'event': 'ok', 'name': 'suite::second'},
    ]).encode()
    receipt = {'commit': commit, 'suite': 'quality', 'requestedGroup': 'server-test',
               'cleanupComplete': True, 'cancelled': False, 'reused': False,
               'requestedPassed': True, 'passed': False, 'checks': {'server-test': {}},
               'runtimeImageId': 'bound-runtime', 'sourceSha256': 'bound-source', 'buildTimestamp': 'bound-time'}

    def archive(path, files):
        path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(path, 'w:gz') as stream:
            for name, value in files.items():
                member = tarfile.TarInfo(name)
                member.size = len(value)
                stream.addfile(member, io.BytesIO(value))

    baseline = tmp_path / 'test-results/nas-parity/followup/candidates/graphato' / commit
    baseline /= 'scenarios/root-private-existing-host/graphato-postdeploy-quality/jenkins-8-artifacts/artifacts.tar.gz'
    archive(baseline, {'server-test.log': log})
    for name, value in {
        'final-state.json': {'original_ci_terminal': True, 'vm_running': False, 'collection_error': None},
        'leroy-run.json': {'status': 'succeeded'},
        'jenkins-start.json': {'number': 1},
        'jenkins-build.json': {'building': False, 'result': 'SUCCESS'},
        **{engine + '-memory-summary.json': {'aligned_guest_host_samples': 12,
            'minimum_host_available_kib': 200 * 1024, 'minimum_host_swap_free_kib': 3000 * 1024}
            for engine in ('leroy', 'jenkins')},
    }.items():
        (case / name).write_text(json.dumps(value))

    def result(engine='leroy', **changes):
        value = {**receipt, **changes}
        path = case / ('leroy-artifacts' if engine == 'leroy' else 'jenkins-1-artifacts') / 'artifacts.tar.gz'
        archive(path, {'result.json': json.dumps(value).encode(), 'server-test.log': log})

    return driver, case, result


@pytest.mark.parametrize('engine', ['leroy', 'jenkins'])
def test_complete_original_rust_group_can_qualify_without_claiming_full_suite(rust_gate, engine):
    driver, case, result = rust_gate
    result(engine)
    value = driver.require_rust_evidence(case, engine)
    assert value['same_full_rust_test_inventory_as_original']
    assert value['rust']['ok'] == 2 and not value['complete_suite_passed']


@pytest.mark.parametrize('changes', [
    {'cleanupComplete': False}, {'reused': True}, {'commit': 'wrong-source'}, {'requestedPassed': False},
])
def test_incomplete_or_unbound_original_rust_result_cannot_start_full_release(rust_gate, changes):
    driver, case, result = rust_gate
    result(**changes)
    with pytest.raises(AssertionError):
        driver.require_rust_evidence(case, 'leroy')


def test_successful_rust_job_with_observed_nas_reserve_undershoot_cannot_start_full_release(rust_gate):
    driver, case, result = rust_gate
    result()
    path = case / 'leroy-memory-summary.json'
    value = json.loads(path.read_text())
    value['minimum_host_swap_free_kib'] = 2304 * 1024 - 1
    path.write_text(json.dumps(value))
    with pytest.raises(AssertionError, match='swap reserve'):
        driver.require_rust_evidence(case, 'leroy')


def test_failed_original_job_cannot_qualify_using_an_older_success_archive(rust_gate):
    driver, case, result = rust_gate
    result()
    (case / 'leroy-run.json').write_text(json.dumps({'status': 'interrupted'}))
    with pytest.raises(AssertionError, match='did not succeed'):
        driver.require_rust_evidence(case, 'leroy')
