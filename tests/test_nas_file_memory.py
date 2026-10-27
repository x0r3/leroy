"""A successful probe never permits different VM RAM backing in the paired CI."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_vm_file_memory as memory  # noqa: E402


@pytest.mark.parametrize('change', [
    {'shared': False}, {'backend': 'anonymous'}, {'size_bytes': 8 * 1024**3},
])
def test_mismatched_or_unverified_ram_backing_cannot_qualify(tmp_path, monkeypatch, change):
    monkeypatch.setattr(memory.vm, 'GUEST_MEMORY_MB', 7168)
    expected = {'backend': 'file', 'size_bytes': 7 * 1024**3, 'shared': True,
                'preallocated': False, 'dump': False, 'host_swap_changed': False, 'qmp_verified': True}
    proof = {'qualified_synthetic_capacity': True, 'all_page_markers_intact': True,
             'allocated_mib': 5888, 'hold_seconds': 60, 'original_fixture_limits_emulated': True,
             'limits': {'memory_bytes': 6 * 1024**3, 'memory_and_swap_bytes': 6 * 1024**3,
                        'nano_cpus': 2 * 10**9, 'cgroup_swap_max': 0}}
    for engine in ('leroy', 'jenkins'):
        (tmp_path / (engine + '-target-before.json')).write_text(json.dumps({'file_memory_configuration': expected}))
        (tmp_path / (engine + '-file-memory-capacity.json')).write_text(json.dumps(proof))
    memory.verify_paired_environment(tmp_path)
    (tmp_path / 'jenkins-target-before.json').write_text(json.dumps({'file_memory_configuration': {**expected, **change}}))
    with pytest.raises(AssertionError):
        memory.verify_paired_environment(tmp_path)


@pytest.mark.parametrize('field,wrong', [
    ('guest_disk_io_throttle', {'read_bps': 0, 'write_bps': 0}),
    ('outer_vm_io_limits', {'BlkioDeviceReadBps': [], 'BlkioDeviceWriteBps': [{'Rate': 33554432}]}),
])
def test_disk_only_qos_requires_actual_disk_rates_and_no_shared_ram_quota(tmp_path, monkeypatch, field, wrong):
    monkeypatch.setattr(memory.vm, 'RESOURCE_PROFILE', memory.vm.DISK_QOS_FILE_MEMORY_PROFILE)
    monkeypatch.setattr(memory.vm, 'GUEST_MEMORY_MB', 7168)
    snapshot = {'file_memory_configuration': {'backend': 'file', 'size_bytes': 7 * 1024**3, 'shared': True,
                'preallocated': False, 'dump': False, 'host_swap_changed': False, 'qmp_verified': True},
                'outer_vm_memory_pressure': {'memory_low_bytes': 4 * 1024**3, 'memory_reservation_bytes': 4 * 1024**3,
                    'memory_high_bytes': 5 * 1024**3, 'cgroup_parent': '-.slice'},
                'guest_disk_io_throttle': {'read_bps': 128 * 1024**2, 'write_bps': 32 * 1024**2},
                'outer_vm_io_limits': {'BlkioDeviceReadBps': [], 'BlkioDeviceWriteBps': []}}
    proof = {'qualified_synthetic_capacity': True, 'all_page_markers_intact': True,
             'allocated_mib': 5888, 'hold_seconds': 60, 'original_fixture_limits_emulated': True,
             'limits': {'memory_bytes': 6 * 1024**3, 'memory_and_swap_bytes': 6 * 1024**3,
                        'nano_cpus': 2 * 10**9, 'cgroup_swap_max': 0}}
    for engine in ('leroy', 'jenkins'):
        for suffix in ('-target-before.json', '-target-after.json'):
            (tmp_path / (engine + suffix)).write_text(json.dumps(snapshot))
        (tmp_path / (engine + '-file-memory-capacity.json')).write_text(json.dumps(proof))
    memory.verify_paired_environment(tmp_path)
    changed = {**snapshot, field: wrong}
    (tmp_path / 'jenkins-target-after.json').write_text(json.dumps(changed))
    with pytest.raises(AssertionError):
        memory.verify_paired_environment(tmp_path)
