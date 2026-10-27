"""Small kernel reservations must not conceal different acceptance hardware."""

import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from compare_nas_full_release import same_guest_resources  # noqa: E402

FIRST = {'cpu_count': 6, 'memory_total_kib': 6060408}
SECOND = {'cpu_count': 6, 'memory_total_kib': 6060392}
BOOT = {engine: {'bios_e820': ['BIOS-e820: [mem 0x0000000100000000-0x00000001ffffffff] usable'],
                 'kernel_memory_lines': ['Memory: 5979776K/6284924K available (304888K reserved)']}
        for engine in ('jenkins', 'leroy')}


def test_larger_reservation_requires_physical_memory_proof():
    assert not same_guest_resources(FIRST, SECOND)
    assert same_guest_resources(FIRST, SECOND, BOOT)


def test_different_cpu_or_ram_budget_is_rejected_despite_matching_boot_proof():
    assert not same_guest_resources(FIRST, {**SECOND, 'cpu_count': 8}, BOOT)
    assert not same_guest_resources(FIRST, {**SECOND, 'memory_total_kib': 4512120}, BOOT)


def test_different_physical_ranges_cannot_justify_kernel_variation():
    data = deepcopy(BOOT)
    data['jenkins']['bios_e820'] = ['different physical RAM map']
    assert not same_guest_resources(FIRST, SECOND, data)


def test_different_kernel_physical_total_or_absent_ranges_is_rejected():
    data = deepcopy(BOOT)
    data['jenkins']['kernel_memory_lines'] = ['Memory: 4979776K/5284924K available (304888K reserved)']
    assert not same_guest_resources(FIRST, SECOND, data)
    data['jenkins']['bios_e820'] = []
    assert not same_guest_resources(FIRST, SECOND, data)
