"""A guard shutdown preserves terminal CI evidence without inventing target health."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import compare_frozen_release_cpu_eight as observer  # noqa: E402
import compare_nas_full_release as release  # noqa: E402


@pytest.mark.parametrize('configured,observed', [(0, 0), (4, 4), (0, 4), (4, 0)])
def test_live_target_verifies_the_selected_reporting_order(monkeypatch, configured, observed):
    monkeypatch.setattr(release, 'PAGE_REPORTING_ORDER', configured)
    monkeypatch.setattr(release, 'POSTGRES_INIT', False)
    monkeypatch.setattr(release.vm, 'RESOURCE_PROFILE', 'nas-6g-ssd-fine-pages')
    monkeypatch.setattr(release.vm, 'VM_IO_LIMITS', None)
    monkeypatch.setattr(release.vm, 'state', lambda: {
        'State': {'Running': True, 'OOMKilled': False, 'ExitCode': 0},
        'HostConfig': {'Memory': 7 * 1024**3, 'MemorySwap': 10 * 1024**3, 'NanoCpus': 6 * 10**9}})

    def guest(command, program, **kwargs):
        if program.startswith('COMMIT='):
            return '{}'
        if 'cpu_count' in program:
            return json.dumps({'cpu_count': 6, 'memory_total_kib': 8000000})
        assert 'page_reporting_order' in program
        return json.dumps({'order': observed})

    monkeypatch.setattr(release.vm, 'guest', guest)
    if configured == observed:
        assert release.target(release.vm.COMMIT)['guest_free_page_reporting']['order'] == observed
    else:
        with pytest.raises(AssertionError):
            release.target(release.vm.COMMIT)


@pytest.fixture
def owned(monkeypatch):
    monkeypatch.setattr(release.vm, 'ROUND', 'qualified-test')
    state = {'State': {'Running': False, 'OOMKilled': False, 'ExitCode': 0},
             'Config': {'Labels': {'io.leroy.nas-release-target': release.vm.COMMIT,
                                  'io.leroy.comparison': 'qualified-test', 'io.leroy.engine': 'leroy'}}}
    monkeypatch.setattr(release.vm, 'state', lambda: state)
    return state


def test_stopped_vm_produces_unavailable_marker_without_guest_read(tmp_path, monkeypatch, owned):
    monkeypatch.setattr(release, 'target', lambda _: pytest.fail('Stopped disk must not be booted or read as live'))
    release.capture_final_target(tmp_path, 'leroy', release.vm.COMMIT)
    assert not (tmp_path / 'leroy-target-after.json').exists()
    marker = json.loads((tmp_path / 'leroy-target-after-unavailable.json').read_text())
    assert marker['available'] is False and marker['original_ci_restarted'] is False
    assert marker['postrun_target_state_verified'] is False
    with pytest.raises(AssertionError, match='first final observation'):
        release.capture_final_target(tmp_path, 'leroy', release.vm.COMMIT)


def test_running_vm_transport_error_is_not_misclassified_as_shutdown(tmp_path, monkeypatch, owned):
    owned['State']['Running'] = True

    def fail(_):
        raise RuntimeError('private-ssh-diagnostic')

    monkeypatch.setattr(release, 'target', fail)
    with pytest.raises(RuntimeError):
        release.capture_final_target(tmp_path, 'leroy', release.vm.COMMIT)
    assert not list(tmp_path.iterdir())


def test_shutdown_during_guest_read_is_recorded(tmp_path, monkeypatch, owned):
    running = copy.deepcopy(owned)
    running['State']['Running'] = True
    states = iter([running, owned])
    monkeypatch.setattr(release.vm, 'state', lambda: next(states))

    def fail(_):
        raise RuntimeError('private-ssh-diagnostic')

    monkeypatch.setattr(release, 'target', fail)
    release.capture_final_target(tmp_path, 'leroy', release.vm.COMMIT)
    text = (tmp_path / 'leroy-target-after-unavailable.json').read_text()
    assert 'private-ssh-diagnostic' not in text


def test_different_target_is_never_certified_as_this_attempt(tmp_path, owned):
    owned['Config']['Labels']['io.leroy.engine'] = 'jenkins'
    with pytest.raises(AssertionError):
        release.capture_final_target(tmp_path, 'leroy', release.vm.COMMIT)
    assert not list(tmp_path.iterdir())


def test_shared_observer_uses_explicit_nas_collector(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(observer.group, 'capture_final_target', lambda *args: seen.append(args), raising=False)
    observer.collect_final_target(tmp_path, 'leroy', release.vm.COMMIT)
    assert seen == [(tmp_path, 'leroy', release.vm.COMMIT)]


@pytest.mark.parametrize('engine', ['leroy', 'jenkins'])
def test_resuming_missing_final_target_does_not_observe_or_restart_original_ci(tmp_path, monkeypatch, engine):
    release.group.write(tmp_path / (engine + '-start.json'), {'production_guard_before': 'retained.json'})
    release.group.write(tmp_path / (engine + '-target-after-unavailable.json'), {'available': False})
    seen = []
    monkeypatch.setattr(observer, 'finish', lambda *args: seen.append(args))
    getattr(observer, engine)(tmp_path, release.vm.COMMIT, 'retained-baseline')
    assert seen == [(tmp_path, engine, 'retained.json')]


def test_incomplete_pair_can_report_stopped_targets_without_original_archives(tmp_path, monkeypatch):
    required = {'web': {'browser-core'}, 'quality': {'server-test'}}
    before = {'manifest': {'commit': release.vm.COMMIT},
              'guest_resources': {'cpu_count': 6, 'memory_total_kib': 10176876},
              'outer_vm_resources': {'Memory': 11 * 1024**3}}
    for engine in ('leroy', 'jenkins'):
        release.group.write(tmp_path / (engine + '-target-before.json'), before)
        release.group.write(tmp_path / (engine + '-target-after-unavailable.json'), {
            'commit': release.vm.COMMIT, 'engine': engine, 'available': False,
            'outer_vm_state': {'Running': False}})
    for job in ('graphato-release-acceptance', 'graphato-postdeploy-web', 'graphato-postdeploy-quality'):
        folder = tmp_path / job
        folder.mkdir()
        release.group.write(folder / 'leroy-run.json', {'status': 'failed', 'artifacts': []})
        release.group.write(folder / 'jenkins-build.json', {'result': 'FAILURE'})
        release.group.write(folder / 'jenkins-artifact-index.json', [])
    monkeypatch.setattr(release, 'qualification_report', lambda *a: {})
    release.analyze_incomplete(tmp_path, required, {}, {}, [])
    report = json.loads((tmp_path / 'analysis.json').read_text())
    assert not report['original_target_after_available_both']
    assert not report['all_original_workloads_successful_both']
    assert not report['production_replacement_ready']
    assert report['targets']['leroy']['after'] is None
