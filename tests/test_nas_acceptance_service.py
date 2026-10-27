"""Crash/response boundaries never become a second original workload."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_acceptance_service as service  # noqa: E402
import nas_open_authorization as grant  # noqa: E402
import nas_resource_window_guard as guard  # noqa: E402
import run_nas_day_window as day  # noqa: E402
from nas_lease_recorder import event  # noqa: E402
from nas_original_workload import resource_ast  # noqa: E402


def test_fresh_phase_can_launch():
    assert service.decision(None, {'LoadState': 'not-found'}) == 'launch'


def test_lost_launch_response_adopts_same_existing_unit():
    assert service.decision({'launch_intent': True}, {'LoadState': 'loaded', 'InvocationID': 'same'}) == 'observe'
    assert service.decision({'invocation_id': 'same'}, {'LoadState': 'loaded', 'InvocationID': 'same'}) == 'observe'


@pytest.mark.parametrize('retained,actual', [
    ({'launch_intent': True}, {'LoadState': 'not-found'}),
    ({'invocation_id': 'original'}, {'LoadState': 'loaded', 'InvocationID': 'replacement'}),
    (None, {'LoadState': 'loaded', 'InvocationID': 'unknown'}),
    (None, {'LoadState': 'error'}),
])
def test_uncertain_or_replaced_units_never_authorize_dispatch(retained, actual):
    with pytest.raises(AssertionError):
        service.decision(retained, actual)


def plan():
    return {'maximum_window_seconds': 14400, 'user_approved': True,
            'comparison_rounds': [day.round_name('rust-leroy', 'v')], 'source_commit': guard.COMMIT,
            'explicit_user_request': grant.REQUEST, 'continuation_authorization': {
                'open_ended': True, 'closed_windows_extended': False, 'authorization_sha256': 'a' * 64},
            'absolute_deadline_epoch': 10000}


def test_open_grant_keeps_finite_four_hour_window_and_recovery(monkeypatch):
    monkeypatch.setattr(guard.time, 'time', lambda: 1000)
    assert guard.window_policy(plan(), day.window_name('rust-leroy', 'v')) == (
        14400, [day.round_name('rust-leroy', 'v')], 900)
    assert day.authorization_end('v') is None
    assert day.authorization_end('u') == day.CONTINUATION_END


@pytest.mark.parametrize('phase', day.PHASES)
def test_new_console_corrected_attempt_is_distinct_and_registered(monkeypatch, phase):
    monkeypatch.setattr(guard.time, 'time', lambda: 1000)
    value = plan()
    case = day.round_name(phase, 'w')
    name = day.window_name(phase, 'w')
    value['comparison_rounds'] = [case]
    assert name != day.window_name(phase, 'v') and case != day.round_name(phase, 'v')
    assert guard.DAY_WINDOWS[name] == [case]
    assert guard.window_policy(value, name) == (14400, [case], 900)
    assert day.authorization_end('w') is None
    assert day.resource_profile('w') == day.resource_profile('v')
    assert day.page_reporting_order('w') == day.page_reporting_order('v')
    monkeypatch.setattr(service, 'ATTEMPT', 'w')
    assert service.unit_name(phase) == 'leroy-acceptance-20261017-w-' + phase


@pytest.mark.parametrize('phase', ('release-leroy', 'release-jenkins'))
def test_new_release_windows_cover_original_suites_without_extending_rust_windows(monkeypatch, phase):
    monkeypatch.setattr(guard.time, 'time', lambda: 1000)
    value = plan()
    value.update(maximum_window_seconds=43200, absolute_deadline_epoch=42000,
                 comparison_rounds=[day.round_name(phase, 'x')])
    assert guard.window_policy(value, day.window_name(phase, 'x')) == (43200, value['comparison_rounds'], 900)
    assert day.maximum_window_seconds('x') == 43200
    assert day.maximum_window_seconds('w') == 14400
    with pytest.raises(AssertionError):
        guard.window_policy(value, day.window_name(phase, 'w'))
    assert day.window_name('rust-leroy', 'x') not in guard.DAY_WINDOWS
    assert day.resource_profile('x') == day.resource_profile('w')


@pytest.mark.parametrize('key,value', [('maximum_window_seconds', 999999),
    ('absolute_deadline_epoch', float('inf')), ('absolute_deadline_epoch', 2000),
    ('explicit_user_request', 'older grant'), ('comparison_rounds', ['other'])])
def test_unlimited_grant_cannot_extend_an_individual_window(monkeypatch, key, value):
    monkeypatch.setattr(guard.time, 'time', lambda: 1000)
    value_plan = plan()
    value_plan[key] = value
    with pytest.raises(AssertionError):
        guard.window_policy(value_plan, day.window_name('rust-leroy', 'v'))


def test_physical_contract_allows_only_classifier_change():
    original = 'RESOURCE=7\ndef ssh_transport_unavailable(r):return False\ndef configure():return RESOURCE\n'
    changed = original.replace('return False', 'return True')
    assert resource_ast(original) == resource_ast(changed)
    assert resource_ast(original) != resource_ast(original.replace('RESOURCE=7', 'RESOURCE=8'))


def test_lease_event_parser_drops_arbitrary_output_and_keeps_bounded_timing():
    assert event('secret-token-in-arbitrary-output') is None
    assert event('2026-10-17T06:00:00Z Leroy lease timing: '
                 '{"event":"local_deadline","unconfirmed_seconds":45,"last_request_seconds":5,"loop_gap_seconds":3}')['event'] == 'local_deadline'
    assert event('2026-10-17T06:00:00Z Leroy lease timing: '
                 '{"event":"local_deadline","authorization":"secret-token"}') is None
