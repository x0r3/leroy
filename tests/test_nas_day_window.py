"""Day authorization must never inherit expired night scope or altered sources."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_nas_day_window as day  # noqa: E402


@pytest.fixture
def approval(monkeypatch, tmp_path):
    monkeypatch.setattr(day, 'ROOT', tmp_path)
    monkeypatch.setattr(day, 'SOURCES', ('driver.py',))
    (tmp_path / 'driver.py').write_text('reviewed')
    monkeypatch.setattr(day.time, 'time', lambda: day.DAY_END - 10000)
    return {'phase': 'rust-leroy', 'user_approved': True, 'explicit_user_request': 'den ganzen Tag',
            'window': day.window_name('rust-leroy'), 'engine': 'leroy',
            'comparison_rounds': [day.round_name('rust-leroy')], 'source_commit': day.vm.COMMIT,
            'maximum_window_seconds': 14400, 'resource_profile': day.vm.GUEST_SWAP_PROFILE,
            'created_at_epoch': day.DAY_END - 11000, 'day_end_epoch': day.DAY_END,
            'absolute_deadline_epoch': day.DAY_END, 'services': list(day.SERVICES),
            'production_cutover': False, 'application_sources_tests_and_fixture_limits_unchanged': True,
            'script_sha256': {'driver.py': day.vm.digest(tmp_path / 'driver.py')}}


@pytest.mark.parametrize('change', [
    {'user_approved': False}, {'explicit_user_request': ''}, {'absolute_deadline_epoch': day.DAY_END + 1},
    {'maximum_window_seconds': 86400}, {'window': 'resource-window-original-night-20261014-f'},
    {'production_cutover': True}, {'services': ['jenkins']}, {'source_commit': 'changed'},
    {'application_sources_tests_and_fixture_limits_unchanged': False},
])
def test_day_permission_has_fixed_service_source_and_end_boundaries(approval, change):
    day.validate_approval(approval)
    with pytest.raises(AssertionError):
        day.validate_approval({**approval, **change})


def test_changed_source_invalidates_prepared_plan(approval, monkeypatch, tmp_path):
    (tmp_path / 'driver.py').write_text('changed')
    with pytest.raises(AssertionError):
        day.validate_approval(approval)


@pytest.mark.parametrize('wrong_order', [0, 9, 4.0, True])
def test_new_page_reporting_attempt_requires_its_reviewed_order(approval, monkeypatch, wrong_order):
    import nas_ci_background

    monkeypatch.setattr(nas_ci_background, 'capacity_proof', lambda: 'capacity-proof')
    monkeypatch.setattr(day, 'control_working_set_binding', lambda: {'deployment_sha256': 'working-set-proof'})
    value = {**approval, 'attempt': 'i', 'window': day.window_name('rust-leroy', 'i'),
             'comparison_rounds': [day.round_name('rust-leroy', 'i')],
             'resource_profile': day.resource_profile('i'), 'matching_ci_background': True,
             'ci_slots': 2, 'ci_capacity_alignment_proof_sha256': 'capacity-proof',
             'control_working_set_binding': {'deployment_sha256': 'working-set-proof'},
             'guest_page_reporting_order': 4}
    day.validate_approval(value)
    with pytest.raises(AssertionError):
        day.validate_approval({**value, 'guest_page_reporting_order': wrong_order})


@pytest.mark.parametrize('change', [
    {'engine_memory_binding': {}}, {'guest_page_reporting_order': 0},
    {'control_working_set_binding': {}}, {'ci_slots': 1},
])
@pytest.mark.parametrize('attempt', ['j', 'k', 'l'])
def test_new_engine_attempt_rejects_missing_resource_and_runtime_proofs(approval, monkeypatch, change, attempt):
    import nas_ci_background

    monkeypatch.setattr(nas_ci_background, 'capacity_proof', lambda: 'capacity-proof')
    monkeypatch.setattr(day, 'control_working_set_binding', lambda: {'proof': 'working-set'})
    monkeypatch.setattr(day, 'engine_memory_binding', lambda: {'proof': 'engine-memory'})
    monkeypatch.setattr(day, 'ssh_transport_binding', lambda *args: {'proof': 'ssh-transport'})
    value = {**approval, 'attempt': attempt, 'window': day.window_name('rust-leroy', attempt),
             'comparison_rounds': [day.round_name('rust-leroy', attempt)], 'resource_profile': day.resource_profile(attempt),
             'matching_ci_background': True, 'ci_slots': 2, 'ci_capacity_alignment_proof_sha256': 'capacity-proof',
             'control_working_set_binding': {'proof': 'working-set'}, 'engine_memory_binding': {'proof': 'engine-memory'},
             'ssh_transport_binding': {'proof': 'ssh-transport'},
             'guest_page_reporting_order': 4}
    day.validate_approval(value)
    with pytest.raises(AssertionError):
        day.validate_approval({**value, **change})


@pytest.mark.parametrize('attempt', ['i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 't', 'u'])
def test_new_jenkins_reference_still_requires_successful_original_leroy_rust(monkeypatch, attempt):
    monkeypatch.setattr(day, 'ATTEMPT', attempt)
    monkeypatch.setattr(day, 'read', lambda path: {'all_seven_original_services_restored_healthy': True,
                                               'source_removed': True})
    import nas_ci_background

    monkeypatch.setattr(nas_ci_background, 'capacity_proof', lambda: 'capacity-proof')
    calls = []

    def missing(engine):
        calls.append(engine)
        raise AssertionError('Fresh original Rust is missing')

    monkeypatch.setattr(day, 'require_day_rust', missing)
    with pytest.raises(AssertionError, match='Fresh original Rust'):
        day.prerequisites('rust-jenkins')
    assert calls == ['leroy']


@pytest.mark.parametrize('change', [
    {'nas_local_capacity': False}, {'local_capacity_binding': {}}, {'continuation_authorization': {}},
    {'absolute_deadline_epoch': day.CONTINUATION_END + 1}, {'maximum_window_seconds': 86400},
    {'explicit_user_request': 'den ganzen Tag'},
])
@pytest.mark.parametrize('attempt', ['m', 'n', 'o'])
def test_continuation_requires_new_scope_and_local_driver_proofs(approval, monkeypatch, change, attempt):
    import nas_ci_background

    monkeypatch.setattr(day.time, 'time', lambda: day.CONTINUATION_END - 10000)
    monkeypatch.setattr(nas_ci_background, 'capacity_proof', lambda: 'capacity')
    monkeypatch.setattr(day, 'control_working_set_binding', lambda: 'control')
    monkeypatch.setattr(day, 'engine_memory_binding', lambda: 'engine')
    monkeypatch.setattr(day, 'ssh_transport_binding', lambda *args: 'ssh')
    monkeypatch.setattr(day, 'local_capacity_binding', lambda *args: 'local')
    monkeypatch.setattr(day, 'continuation_binding', lambda: 'authorization')
    value = {**approval, 'attempt': attempt, 'window': day.window_name('rust-leroy', attempt),
             'comparison_rounds': [day.round_name('rust-leroy', attempt)], 'resource_profile': day.resource_profile(attempt),
             'explicit_user_request': day.CONTINUATION_REQUEST, 'day_end_epoch': day.CONTINUATION_END,
             'created_at_epoch': day.CONTINUATION_END - 11000, 'absolute_deadline_epoch': day.CONTINUATION_END,
             'matching_ci_background': True, 'ci_slots': 2, 'ci_capacity_alignment_proof_sha256': 'capacity',
             'guest_page_reporting_order': 4, 'control_working_set_binding': 'control', 'engine_memory_binding': 'engine',
             'ssh_transport_binding': 'ssh', 'local_capacity_binding': 'local', 'continuation_authorization': 'authorization',
             'nas_local_capacity': True}
    day.validate_approval(value)
    with pytest.raises(AssertionError):
        day.validate_approval({**value, **change})


def test_old_windows_cannot_inherit_next_day_end():
    assert day.authorization_end('l') == day.DAY_END
    assert day.authorization_end('m') == day.CONTINUATION_END
    assert day.authorization_end('n') == day.CONTINUATION_END
    assert day.authorization_end('o') == day.CONTINUATION_END
    assert day.authorization_end('p') == day.CONTINUATION_END
    assert day.authorization_end('q') == day.CONTINUATION_END
    assert day.authorization_end('r') == day.CONTINUATION_END
    assert day.authorization_end('t') == day.CONTINUATION_END
    assert day.authorization_end('u') == day.CONTINUATION_END


@pytest.mark.parametrize('attempt', ['q', 'r', 't', 'u', 'y'])
def test_imported_driver_uses_approval_attempt_for_its_original_binding(approval, monkeypatch, attempt):
    import nas_ci_background
    import nas_graphato_transport

    monkeypatch.setattr(day, 'ATTEMPT', 'a')  # An imported CLI module has this default.
    monkeypatch.setattr(day.time, 'time', lambda: day.CONTINUATION_END - 10000)
    monkeypatch.setattr(nas_ci_background, 'capacity_proof', lambda: 'capacity')
    monkeypatch.setattr(day, 'control_working_set_binding', lambda: 'control')
    monkeypatch.setattr(day, 'engine_memory_binding', lambda: 'engine')
    monkeypatch.setattr(day, 'ssh_transport_binding', lambda *args: 'ssh')
    monkeypatch.setattr(day, 'continuation_binding', lambda: 'authorization')
    monkeypatch.setattr(nas_graphato_transport, 'binding', lambda: 'transport')
    import nas_vm_dns

    monkeypatch.setattr(nas_vm_dns, 'reference_binding', lambda: 'dns-reference')
    calls = []

    def original_binding(*args, **kwargs):
        calls.append(kwargs['attempt'])
        return 'fresh-upstream-gates'

    monkeypatch.setattr(day, 'original_workload_binding', original_binding)
    phase = 'rust-jenkins' if attempt == 'y' else 'rust-leroy'
    value = {**approval, 'attempt': attempt, 'phase': phase, 'engine': phase.rsplit('-', 1)[1],
             'window': day.window_name(phase, attempt),
             'comparison_rounds': [day.round_name(phase, attempt)], 'resource_profile': day.resource_profile(attempt),
             'explicit_user_request': day.CONTINUATION_REQUEST, 'day_end_epoch': day.CONTINUATION_END,
             'created_at_epoch': day.CONTINUATION_END - 11000, 'absolute_deadline_epoch': day.CONTINUATION_END,
             'matching_ci_background': True, 'ci_slots': 2, 'ci_capacity_alignment_proof_sha256': 'capacity',
             'guest_page_reporting_order': 4, 'control_working_set_binding': 'control', 'engine_memory_binding': 'engine',
             'ssh_transport_binding': 'ssh', 'original_workload_qualification': True,
             'original_workload_binding': 'fresh-upstream-gates', 'graphato_transport_binding': 'transport',
             'continuation_authorization': 'authorization'}
    if attempt in {'t', 'u', 'y'}:
        value.update(guest_dns_policy=nas_vm_dns.POLICY, dns_failure_reference='dns-reference')
    if attempt == 'y':
        import nas_console_binding
        from nas_open_authorization import REQUEST

        monkeypatch.setattr(nas_console_binding, 'binding', lambda: 'console')
        monkeypatch.setattr(day, 'open_authorization_binding', lambda *_: 'authorization')
        def explicit_failed_reference(selected):
            assert selected == 'y'
            return 'failed-W'
        monkeypatch.setattr(day, 'failed_original_reference_binding', explicit_failed_reference)
        value.update(explicit_user_request=REQUEST, day_end_epoch=None, console_logging_binding='console',
                     diagnostic_reference_only=True, failed_original_leroy_reference='failed-W')
    day.validate_approval(value)
    assert calls == [attempt]


@pytest.mark.parametrize('change', [
    {'original_workload_qualification': False}, {'original_workload_binding': {}},
    {'nas_local_capacity': True}, {'separate_capacity_reference': {'qualified': True}},
    {'application_sources_tests_and_fixture_limits_unchanged': False}, {'ci_slots': 1},
    {'continuation_authorization': {}},
])
def test_original_workload_plan_preserves_original_jobs_and_negative_stress(approval, monkeypatch, change):
    import nas_ci_background

    monkeypatch.setattr(day.time, 'time', lambda: day.CONTINUATION_END - 10000)
    monkeypatch.setattr(nas_ci_background, 'capacity_proof', lambda: 'capacity')
    monkeypatch.setattr(day, 'control_working_set_binding', lambda: 'control')
    monkeypatch.setattr(day, 'engine_memory_binding', lambda: 'engine')
    monkeypatch.setattr(day, 'ssh_transport_binding', lambda *args: 'ssh')
    monkeypatch.setattr(day, 'original_workload_binding', lambda: {'synthetic_capacity_qualified': False})
    monkeypatch.setattr(day, 'continuation_binding', lambda: 'authorization')
    value = {**approval, 'attempt': 'p', 'window': day.window_name('rust-leroy', 'p'),
             'comparison_rounds': [day.round_name('rust-leroy', 'p')], 'resource_profile': day.resource_profile('p'),
             'explicit_user_request': day.CONTINUATION_REQUEST, 'day_end_epoch': day.CONTINUATION_END,
             'created_at_epoch': day.CONTINUATION_END - 11000, 'absolute_deadline_epoch': day.CONTINUATION_END,
             'matching_ci_background': True, 'ci_slots': 2, 'ci_capacity_alignment_proof_sha256': 'capacity',
             'guest_page_reporting_order': 4, 'control_working_set_binding': 'control', 'engine_memory_binding': 'engine',
             'ssh_transport_binding': 'ssh', 'original_workload_qualification': True,
             'original_workload_binding': {'synthetic_capacity_qualified': False},
             'continuation_authorization': 'authorization'}
    day.validate_approval(value)
    with pytest.raises(AssertionError):
        day.validate_approval({**value, **change})


def test_jenkins_and_full_releases_cannot_bypass_successful_original_rust(monkeypatch):
    monkeypatch.setattr(day, 'read', lambda path: {'all_seven_original_services_restored_healthy': True})
    required = []

    def absent(case, engine):
        required.append(engine)
        raise AssertionError('Original Rust evidence missing')

    monkeypatch.setattr(day, 'require_rust_evidence', absent)
    for phase in day.PHASES[1:]:
        with pytest.raises(AssertionError, match='Original Rust'):
            day.prerequisites(phase)
    assert required == ['leroy'] * 3


def test_explicit_failed_reference_allows_only_the_new_jenkins_diagnostic(monkeypatch):
    import nas_ci_background

    monkeypatch.setattr(day, 'ATTEMPT', 'p')
    monkeypatch.setattr(day, 'DIAGNOSTIC_REFERENCE', True)
    monkeypatch.setattr(day, 'read', lambda path: {'all_seven_original_services_restored_healthy': True, 'source_removed': True})
    monkeypatch.setattr(nas_ci_background, 'capacity_proof', lambda: 'proof')
    calls = []
    monkeypatch.setattr(day, 'failed_original_reference_binding', lambda: calls.append('failed-reference'))
    monkeypatch.setattr(day, 'require_day_rust', lambda engine: pytest.fail('Not a successful Rust waiver'))
    day.prerequisites('rust-jenkins')
    assert calls == ['failed-reference']
    for phase in ('rust-leroy', 'release-leroy', 'release-jenkins'):
        with pytest.raises(AssertionError, match='cannot waive'):
            day.prerequisites(phase)


def test_day_recovery_waits_for_verified_vm_stop_before_verifying_app_health(monkeypatch):
    phases = iter(['restore_error', 'restore_error', 'restored'])
    sleeps = []
    monkeypatch.setattr(day, 'action', lambda remote, action, **kwargs: {'phase': next(phases)})
    monkeypatch.setattr(day.time, 'sleep', sleeps.append)
    assert day.restore_until_finished('own-window')['phase'] == 'restored'
    assert sleeps == [15, 15]


def test_recovery_transport_timeout_retries_same_journal_without_reopening(monkeypatch, tmp_path):
    calls, sleeps = [], []

    def action(remote, name, **kwargs):
        calls.append((remote, name, kwargs['operation_timeout']))
        if len(calls) == 1:
            raise subprocess.TimeoutExpired('secret SSH command', 420)
        return {'phase': 'restored'}

    monkeypatch.setattr(day, 'action', action)
    monkeypatch.setattr(day.time, 'sleep', sleeps.append)
    assert day.restore_until_finished('same-owned-journal', folder=tmp_path)['phase'] == 'restored'
    assert calls == [('same-owned-journal', 'restore', 400)] * 2 and sleeps == [15]
    error = json.loads((tmp_path / 'recovery-observation-errors.jsonl').read_text())
    assert error['outcome_unknown'] and error['error_type'] == 'TimeoutExpired'
    assert not error['original_ci_restarted'] and 'secret' not in json.dumps(error)


def test_recovery_rpcs_cannot_overrun_fixed_recovery_budget(monkeypatch):
    elapsed = [0]
    limits = []

    def action(remote, name, **kwargs):
        assert (remote, name) == ('same-owned-journal', 'restore')
        limit = kwargs['operation_timeout']
        limits.append(limit)
        elapsed[0] += limit + 20
        raise subprocess.TimeoutExpired('SSH', limit + 20)

    monkeypatch.setattr(day.time, 'monotonic', lambda: elapsed[0])
    monkeypatch.setattr(day.time, 'sleep', lambda value: elapsed.__setitem__(0, elapsed[0] + value))
    monkeypatch.setattr(day, 'action', action)
    with pytest.raises(RuntimeError, match='Recovery remains incomplete'):
        day.restore_until_finished('same-owned-journal')
    assert elapsed[0] <= 900 and limits == [400, 400, 10]


def test_recovery_never_starts_rpc_beyond_authorized_end(monkeypatch):
    monkeypatch.setattr(day.time, 'time', lambda: 1000)
    monkeypatch.setattr(day, 'action', lambda *a, **kw: pytest.fail('No time remains for a verified recovery RPC'))
    with pytest.raises(RuntimeError, match='Recovery remains incomplete'):
        day.restore_until_finished('same-owned-journal', deadline_epoch=1020)


def test_recovery_rpc_limit_reduces_both_remote_process_and_transport(monkeypatch):
    import run_nas_full_release_window as window

    calls = []

    def remote(program, **kwargs):
        calls.append((program, kwargs))
        return '{"phase":"restored"}'

    monkeypatch.setattr(window.vm, 'remote', remote)
    assert window.action('same-owned-journal', 'restore', operation_timeout=20)['phase'] == 'restored'
    assert len(calls) == 1 and 'timeout=20)' in calls[0][0] and calls[0][1] == {'sudo': True, 'timeout': 40}


@pytest.mark.parametrize(('action', 'limit'), [('restore', 0), ('restore', 401), ('restore', True), ('pause', 400), ('register', 1)])
def test_recovery_rpc_cannot_extend_deadlines_or_change_other_operations(monkeypatch, action, limit):
    import run_nas_full_release_window as window

    monkeypatch.setattr(window.vm, 'remote', lambda *a, **kw: pytest.fail('Invalid override must not reach NAS'))
    with pytest.raises(AssertionError):
        window.action('same-owned-journal', action, operation_timeout=limit)
