"""Changing a guest kernel parameter must never target the physical NAS."""

import builtins
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_vm_page_reporting as reporting  # noqa: E402


def execute(*, uid=0, ready=True, virtualization='kvm', baseline=9, previous=None, writes=None, order=reporting.ORDER):
    writes = writes if writes is not None else []
    parameter = [baseline]
    output = []

    class GuestPath:
        def __init__(self, path):
            self.path = path

        def is_file(self):
            return ready if self.path == '/var/lib/leroy-vm/ready' else True

        def is_symlink(self):
            return False

        def glob(self, pattern):
            assert self.path == '/sys/bus/virtio/devices' and pattern == '*/driver'
            return [SimpleNamespace(resolve=lambda: SimpleNamespace(name='virtio_balloon'))]

        def read_text(self):
            return {'/sys/module/page_reporting/parameters/page_reporting_order': str(parameter[0]),
                    '/proc/sys/kernel/random/boot_id': 'original-guest-boot',
                    '/proc/meminfo': 'MemTotal: 6060400 kB\nSwapTotal: 0 kB\nMemFree: 4194304 kB\n',
                    '/proc/buddyinfo': 'fixed buddy counters\n'}[self.path]

        def write_text(self, value):
            writes.append((self.path, value))
            parameter[0] = int(value)

    def detect(command, *, text):
        assert command == ['systemd-detect-virt'] and text
        return virtualization

    modules = {'json': json, 'os': SimpleNamespace(geteuid=lambda: uid, sysconf=lambda _: 4096),
               'pathlib': SimpleNamespace(Path=GuestPath), 'subprocess': SimpleNamespace(check_output=detect),
               'time': SimpleNamespace(sleep=lambda _: None)}
    environment = {**vars(builtins), '__import__': lambda name, *args: modules[name], 'print': output.append}
    exec(reporting.PROGRAM, {'__builtins__': environment, 'ORDER': order, 'PREVIOUS': previous})
    return json.loads(output[0]), writes


@pytest.mark.parametrize('options', [{'uid': 1000}, {'ready': False}, {'virtualization': 'none'},
                                     {'virtualization': 'docker'}, {'baseline': 8}])
def test_unsafe_target_or_unexpected_baseline_is_preserved(options):
    writes = []
    with pytest.raises(AssertionError):
        execute(**options, writes=writes)
    assert writes == []


def test_reporting_changes_only_free_page_granularity_without_balloon_inflation():
    result, writes = execute()
    assert writes == [('/sys/module/page_reporting/parameters/page_reporting_order', '4\n')]
    assert result['minimum_reported_block_bytes'] == 65536
    assert result['guest_memory_kib']['MemTotal'] == 6060400
    assert result['guest_capacity_changed'] is False and result['host_kernel_modified'] is False


def test_resuming_other_guest_boot_cannot_change_parameters():
    writes = []
    with pytest.raises(AssertionError):
        execute(baseline=4, previous={'guest_boot_id': 'another-boot', 'original_order': 9}, writes=writes)
    assert writes == []


def test_order_zero_reports_single_pages_with_unchanged_guest_capacity():
    result, writes = execute(order=0)
    assert writes == [('/sys/module/page_reporting/parameters/page_reporting_order', '0\n')]
    assert result['minimum_reported_block_bytes'] == 4096
    assert result['guest_memory_kib']['MemTotal'] == 6060400
    assert not result['guest_capacity_changed'] and not result['host_kernel_modified']


@pytest.mark.parametrize('order', [-1, 1, 9, True, '0'])
def test_unsupported_order_never_contacts_a_vm(monkeypatch, tmp_path, order):
    monkeypatch.setattr(reporting.vm, 'state', lambda: pytest.fail('No VM may be contacted'))
    with pytest.raises(AssertionError):
        reporting.apply_guest_page_reporting(tmp_path, 'leroy', order=order)


def test_resume_cannot_silently_switch_reporting_order(monkeypatch, tmp_path):
    folder = tmp_path / 'own-round'
    folder.mkdir()
    (folder / 'leroy-guest-page-reporting.json').write_text(json.dumps({'configured_order': 4}))
    monkeypatch.setattr(reporting.vm, 'ROUND', folder.name)
    monkeypatch.setattr(reporting.vm, 'state', lambda: {'State': {'Running': True},
        'Config': {'Labels': {'io.leroy.comparison': folder.name, 'io.leroy.engine': 'leroy',
                             'io.leroy.nas-release-target': reporting.vm.COMMIT}}})
    monkeypatch.setattr(reporting.vm, 'guest', lambda *a, **kw: pytest.fail('Retain the existing order'))
    with pytest.raises(AssertionError):
        reporting.apply_guest_page_reporting(folder, 'leroy', order=0)


@pytest.mark.parametrize('running,engine,namespace,commit', [
    (False, 'leroy', 'own-round', reporting.vm.COMMIT),
    (True, 'jenkins', 'own-round', reporting.vm.COMMIT),
    (True, 'leroy', 'foreign-round', reporting.vm.COMMIT),
    (True, 'leroy', 'own-round', 'a' * 40),
])
def test_wrong_container_identity_is_rejected_before_any_ssh(monkeypatch, tmp_path, running, engine, namespace, commit):
    folder = tmp_path / 'own-round'
    monkeypatch.setattr(reporting.vm, 'ROUND', folder.name)
    monkeypatch.setattr(reporting.vm, 'state', lambda: {'State': {'Running': running},
        'Config': {'Labels': {'io.leroy.comparison': namespace, 'io.leroy.engine': engine,
                             'io.leroy.nas-release-target': commit}}})
    monkeypatch.setattr(reporting.vm, 'guest', lambda *args, **kwargs: pytest.fail('No guest may be contacted'))
    with pytest.raises(AssertionError):
        reporting.apply_guest_page_reporting(folder, 'leroy')
