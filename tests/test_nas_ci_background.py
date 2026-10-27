"""A comparison must reject changed capacity or a restarted CI background."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import compare_frozen_release_cpu_eight as release  # noqa: E402
import nas_ci_background as background  # noqa: E402
import run_nas_day_window as day  # noqa: E402


def live():
    return ([{'numExecutors': 2, 'offline': False}],
            [{'id': 'runner-nas-parity', 'capacity': 2, 'online': True}])


@pytest.mark.parametrize('change', ['jenkins-one', 'runner-one', 'offline', 'duplicate', 'extra-agent'])
def test_live_capacity_rejects_unmatched_or_unavailable_workers(change):
    computers, runners = live()
    background.validate_live_capacity(computers, runners)
    if change == 'jenkins-one':
        computers[0]['numExecutors'] = 1
    elif change == 'runner-one':
        runners[0]['capacity'] = 1
    elif change == 'offline':
        runners[0]['online'] = False
    elif change == 'duplicate':
        runners.append(dict(runners[0]))
    else:
        computers.append(dict(computers[0]))
    with pytest.raises(AssertionError):
        background.validate_live_capacity(computers, runners)


def test_background_restart_cannot_be_reported_as_equal(tmp_path, monkeypatch):
    state = {'private_jenkins_process': {'pid': 10}, 'leroy_runner_capacity': 2}
    monkeypatch.setattr(background, 'snapshot', lambda: state)
    background.record(tmp_path, 'leroy', 'before')
    state['private_jenkins_process']['pid'] = 11
    with pytest.raises(AssertionError, match='process changed'):
        background.record(tmp_path, 'leroy', 'after')
    assert not (tmp_path / 'leroy-ci-background-after.json').exists()


@pytest.mark.parametrize('keep', [False, True])
def test_jenkins_background_mode_preserves_legacy_cleanup(tmp_path, monkeypatch, keep):
    (tmp_path / 'jenkins-start.json').write_text(json.dumps({'builds': {job: 1 for job in release.JOBS}}))
    monkeypatch.setattr(release.group, 'original_jenkins_state', lambda *args: {'started': True, 'building': False})
    monkeypatch.setattr(release.group, 'collect_jenkins', lambda *args: None)
    monkeypatch.setattr(release, 'idle', lambda: None)
    monkeypatch.setattr(release, 'finish', lambda *args: None)
    monkeypatch.setattr(release, 'collect_final_target', lambda *args: None)
    operations = []
    monkeypatch.setattr(release, 'inner', lambda *args, **kwargs: operations.append(args))
    release.jenkins(tmp_path, 'frozen', 'baseline', keep_private_jenkins=keep)
    assert operations == ([] if keep else [('stop', '--time', '120', 'jenkins-parity')])


def test_full_day_plan_cannot_bypass_matching_ci_background(tmp_path, monkeypatch):
    monkeypatch.setattr(day, 'ROOT', tmp_path)
    monkeypatch.setattr(day, 'SOURCES', ())
    monkeypatch.setattr(day.time, 'time', lambda: day.DAY_END - 1000)
    monkeypatch.setattr(background, 'capacity_proof', lambda: 'qualified-capacity-proof')
    value = {'phase': 'release-leroy', 'user_approved': True, 'explicit_user_request': 'den ganzen Tag',
             'window': day.window_name('release-leroy'), 'engine': 'leroy',
             'comparison_rounds': [day.round_name('release-leroy')], 'source_commit': day.vm.COMMIT,
             'maximum_window_seconds': 14400, 'resource_profile': day.vm.GUEST_SWAP_PROFILE,
             'created_at_epoch': day.DAY_END - 2000, 'day_end_epoch': day.DAY_END,
             'absolute_deadline_epoch': day.DAY_END, 'services': list(day.SERVICES),
             'production_cutover': False, 'application_sources_tests_and_fixture_limits_unchanged': True,
             'script_sha256': {}, 'matching_ci_background': True, 'ci_slots': 2,
             'ci_capacity_alignment_proof_sha256': 'qualified-capacity-proof'}
    day.validate_approval(value)
    for change in ({'matching_ci_background': False}, {'ci_slots': 1},
                   {'ci_capacity_alignment_proof_sha256': 'stale-proof'}):
        with pytest.raises(AssertionError):
            day.validate_approval({**value, **change})


@pytest.mark.parametrize('attempt', ['b', 'c', 'd', 'e', 'f', 'g'])
def test_new_attempt_cannot_reuse_old_window_or_larger_guest(monkeypatch, tmp_path, attempt):
    monkeypatch.setattr(day, 'ROOT', tmp_path)
    monkeypatch.setattr(day, 'SOURCES', ())
    monkeypatch.setattr(day.time, 'time', lambda: day.DAY_END - 1000)
    monkeypatch.setattr(background, 'capacity_proof', lambda: 'proof')
    import nas_vm_capacity_reference as reference

    monkeypatch.setattr(reference, 'binding', lambda profile=None: {'qualified': 'separate'})
    value = {'phase': 'rust-leroy', 'attempt': attempt, 'user_approved': True,
             'explicit_user_request': 'den ganzen Tag', 'window': day.window_name('rust-leroy', attempt),
             'engine': 'leroy', 'comparison_rounds': [day.round_name('rust-leroy', attempt)],
             'source_commit': day.vm.COMMIT, 'maximum_window_seconds': 14400,
             'resource_profile': day.resource_profile(attempt),
             'created_at_epoch': day.DAY_END - 2000, 'day_end_epoch': day.DAY_END,
             'absolute_deadline_epoch': day.DAY_END, 'services': list(day.SERVICES),
             'production_cutover': False, 'application_sources_tests_and_fixture_limits_unchanged': True,
             'script_sha256': {}, 'matching_ci_background': True, 'ci_slots': 2,
             'ci_capacity_alignment_proof_sha256': 'proof'}
    if attempt == 'f':
        value['separate_capacity_reference'] = reference.binding()
    day.validate_approval(value)
    for change in ({'window': day.window_name('rust-leroy', 'a')},
                   {'resource_profile': day.vm.GUEST_SWAP_PROFILE},
                   {'comparison_rounds': [day.round_name('rust-leroy', 'a')]},
                   {'matching_ci_background': False}):
        with pytest.raises(AssertionError):
            day.validate_approval({**value, **change})


def test_resume_observation_never_waits_for_its_own_active_ci_run(monkeypatch, tmp_path):
    (tmp_path / 'leroy-start.json').write_text('{"id":"retained-original"}')
    monkeypatch.setattr(background, 'start_jenkins', lambda: None)
    monkeypatch.setattr(background, 'idle', lambda: pytest.fail('Original CI is still active'))
    monkeypatch.setattr(background, 'record', lambda folder, engine, boundary: 'same-live-background')
    assert background.prepare(tmp_path, 'leroy') == 'same-live-background'


@pytest.mark.parametrize('changed_file,change', [
    ('restored-window.json', {'host_reserve_stop': {'reason': 'host_swap_reserve'}}),
    ('prepared.json', {'resource_profile': 'nas-8g-ssd-guest-swap-3840'}),
    ('prepared.json', {'matching_ci_background': False}),
    ('window-result.json', {'native_jenkins_quiet': False}),
])
def test_closed_day_qualification_rejects_hidden_resource_or_background_changes(
    monkeypatch, changed_file, change,
):
    monkeypatch.setattr(day, 'ATTEMPT', 'b')
    monkeypatch.setattr(day, 'require_rust_evidence', lambda *args: {'original_rust_passed': True})
    monkeypatch.setattr(background, 'capacity_proof', lambda: 'proof')
    values = {
        'window-result.json': {key: True for key in (
            'original_rust_qualified', 'all_seven_original_services_restored_healthy',
            'native_jenkins_quiet', 'infrastructure_unchanged', 'controller_process_unchanged',
            'controller_no_new_oom')},
        'closed-disk-archive.json': {'source_removed': True}, 'restored-window.json': {},
        'prepared.json': {'resource_profile': day.vm.BOUNDED_GUEST_SWAP_PROFILE,
                          'matching_ci_background': True, 'ci_slots': 2},
        'leroy-ci-background-before.json': {'capacity_alignment_proof_sha256': 'proof'},
        'leroy-ci-background-after.json': {'capacity_alignment_proof_sha256': 'proof'},
    }
    monkeypatch.setattr(day, 'read', lambda path: values[path.name])
    assert day.require_day_rust('leroy')['original_rust_passed']
    values[changed_file].update(change)
    with pytest.raises(AssertionError):
        day.require_day_rust('leroy')
