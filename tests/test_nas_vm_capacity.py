"""The capacity probe must refuse allocation before the NAS safety reserves."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import probe_nas_vm_capacity as capacity  # noqa: E402


@pytest.mark.parametrize('available_delta,swap_delta,admitted', [
    (128, 768, True),
    (128, 767, False),
    (127, 768, False),
    (0, 4096, False),
    (4096, 0, False),
    (-1, 4096, False),
])
def test_next_step_preserves_swap_budget_and_ram_margin(available_delta, swap_delta, admitted):
    memory = {'MemAvailable': (capacity.vm.MIN_HOST_AVAILABLE_MB + available_delta) * 1024,
              'SwapFree': (capacity.vm.MIN_HOST_SWAP_MB + swap_delta) * 1024}
    assert capacity.admit_host(memory) is admitted
