"""Cache relief may act only inside the owned, ready KVM test guest."""

import builtins
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_vm_cache as cache  # noqa: E402


@pytest.mark.parametrize('label_changes', [{}, {'io.leroy.comparison': 'other'}, {'io.leroy.engine': 'other'}])
def test_stopped_guest_diagnostics_cannot_block_original_result_analysis(monkeypatch, tmp_path, label_changes):
    monkeypatch.setattr(cache.vm, 'ROUND', 'owned-round')
    labels = {'io.leroy.comparison': 'owned-round', 'io.leroy.engine': 'jenkins', **label_changes}
    monkeypatch.setattr(cache.vm, 'state', lambda: {'State': {'Running': False}, 'Config': {'Labels': labels}})
    monkeypatch.setattr(cache.vm, 'guest', lambda *a, **kw: pytest.fail('Never reboot or contact a stopped guest'))
    if label_changes:
        with pytest.raises(AssertionError):
            cache.collect_guest_guard(tmp_path, 'jenkins')
        assert not list(tmp_path.iterdir())
    else:
        proof = cache.collect_guest_guard(tmp_path, 'jenkins')
        path = tmp_path / 'jenkins-guest-cache-observations-unavailable.json'
        assert not proof['available'] and not proof['original_ci_restarted']
        assert json.loads(path.read_text()) == proof
        original = path.stat().st_mtime_ns
        cache.collect_guest_guard(tmp_path, 'jenkins')
        assert path.stat().st_mtime_ns == original


def execute_guest(*, uid=0, ready=True, virtualization='kvm', available=2048, cached=1024):
    writes = []
    sleeps = []
    output = []
    info = (f'MemTotal: 6291456 kB\nMemAvailable: {available * 1024} kB\n'
            f'MemFree: 1048576 kB\nCached: {cached * 1024} kB\nDirty: 8192 kB\nWriteback: 1024 kB\n')

    class GuestPath:
        def __init__(self, path):
            self.path = path

        def is_file(self):
            assert self.path == '/var/lib/leroy-vm/ready'
            return ready

        def read_text(self):
            assert self.path == '/proc/meminfo'
            return info

        def write_text(self, value):
            assert self.path == '/proc/sys/vm/drop_caches'
            writes.append((self.path, value))

    def detect(command, *, text):
        assert command == ['systemd-detect-virt'] and text
        return virtualization

    modules = {'json': json, 'os': SimpleNamespace(geteuid=lambda: uid),
               'pathlib': SimpleNamespace(Path=GuestPath),
               'subprocess': SimpleNamespace(check_output=detect),
               'time': SimpleNamespace(sleep=sleeps.append)}
    environment = {**vars(builtins), '__import__': lambda name, *args: modules[name],
                   'print': output.append}
    exec(cache.GUEST_PROGRAM, {'__builtins__': environment})
    return json.loads(output[0]), writes, sleeps


@pytest.mark.parametrize('options', [{'uid': 1000}, {'ready': False}, {'virtualization': 'none'},
                                     {'virtualization': 'docker'}])
def test_guest_refuses_unprivileged_unready_and_non_kvm_execution(options):
    with pytest.raises(AssertionError):
        execute_guest(**options)


@pytest.mark.parametrize('options', [{'available': 1023}, {'cached': 767}])
def test_guest_preserves_cache_when_available_memory_or_cache_is_too_small(options):
    result, writes, sleeps = execute_guest(**options)
    assert not result['clean_cache_relief_performed']
    assert writes == [] and sleeps == []


def test_ready_guest_releases_only_clean_cache_and_records_dirty_pages():
    result, writes, sleeps = execute_guest(available=1024, cached=768)
    assert result['clean_cache_relief_performed']
    assert writes == [('/proc/sys/vm/drop_caches', '1\n')] and sleeps == [2]
    assert result['guest_before_kib']['Dirty'] == result['guest_after_kib']['Dirty'] == 8192
    assert result['host_kernel_modified'] is False


def test_host_reserve_boundary_does_not_trigger_unnecessary_guest_action(monkeypatch):
    monkeypatch.setattr(cache.vm, 'MIN_HOST_SWAP_MB', 2304)
    assert not cache.host_needs_cache_relief({'SwapFree': 4352 * 1024})
    assert cache.host_needs_cache_relief({'SwapFree': 4352 * 1024 - 1})


@pytest.mark.parametrize('running,round_name', [(False, 'own-round'), (True, 'other-round')])
def test_stopped_or_other_comparison_guest_cannot_be_modified(monkeypatch, running, round_name):
    monkeypatch.setattr(cache.vm, 'ROUND', 'own-round')
    monkeypatch.setattr(cache.vm, 'state', lambda: {'State': {'Running': running},
                                                'Config': {'Labels': {'io.leroy.comparison': round_name}}})
    monkeypatch.setattr(cache.vm, 'guest', lambda *args, **kwargs: pytest.fail('Guest must not be contacted'))
    with pytest.raises(AssertionError):
        cache.relieve_cache()


@pytest.mark.parametrize('namespace,engine', [('other/../guest', 'leroy'), ('own-round', 'production')])
def test_guest_guard_refuses_unsafe_namespace_or_engine(monkeypatch, namespace, engine):
    monkeypatch.setattr(cache.vm, 'ROUND', namespace)
    with pytest.raises(AssertionError):
        cache.guard_root(engine)


def test_guest_guard_stops_on_policy_failure_without_logging_secret_text(monkeypatch, capsys):
    monkeypatch.setattr(cache, 'GUEST_PROGRAM', "raise PermissionError('sensitive error detail')")
    with pytest.raises(SystemExit) as error:
        exec(cache.guard_program(), {})
    assert error.value.code == 1
    output = capsys.readouterr().out
    assert json.loads(output)['policy_error'] == 'PermissionError'
    assert 'sensitive error detail' not in output
