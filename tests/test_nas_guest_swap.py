"""Candidate VM swap must preserve ownership boundaries and paired environment proof."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import compare_nas_full_release as compare  # noqa: E402
import nas_vm_guest_swap as swap  # noqa: E402


@pytest.mark.parametrize('change', [
    {'profile': 'nas-8g-ssd-soft-ram-3840'}, {'running': False}, {'commit': 'foreign'},
    {'round': 'foreign'}, {'engine': 'jenkins'},
])
def test_unowned_or_old_profile_never_creates_guest_swap(monkeypatch, tmp_path, change):
    value = {'profile': swap.vm.GUEST_SWAP_PROFILE, 'running': True, 'commit': swap.vm.COMMIT,
             'round': tmp_path.name, 'engine': 'leroy', **change}
    monkeypatch.setattr(swap.vm, 'ROUND', tmp_path.name)
    monkeypatch.setattr(swap.vm, 'RESOURCE_PROFILE', value['profile'])
    monkeypatch.setattr(swap.vm, 'state', lambda: {'State': {'Running': value['running']}, 'Config': {'Labels': {
        'io.leroy.nas-release-target': value['commit'], 'io.leroy.comparison': value['round'], 'io.leroy.engine': value['engine']}}})
    monkeypatch.setattr(swap.vm, 'guest', lambda *a, **kw: pytest.fail('No write to an unreviewed guest'))
    with pytest.raises(AssertionError):
        swap.apply_guest_swap(tmp_path, 'leroy')


@pytest.mark.parametrize('change', [{'priority': 0}, {'file_bytes': 2 * 1024**3}, {'swappiness': 200}])
def test_original_pair_cannot_hide_different_guest_swap_configuration(monkeypatch, tmp_path, change):
    monkeypatch.setattr(compare.vm, 'RESOURCE_PROFILE', swap.vm.GUEST_SWAP_PROFILE)
    config = {'path': '/var/lib/leroy-vm/guest-swap/swapfile', 'file_bytes': 4 * 1024**3,
              'kernel_swap_kib': 4 * 1024**2 - 4, 'priority': 10, 'swappiness': 60}
    for engine in ('leroy', 'jenkins'):
        (tmp_path / (engine + '-target-before.json')).write_text(json.dumps({'guest_swap_configuration': config}))
    compare.verify_guest_swap_environment(tmp_path)
    (tmp_path / 'jenkins-target-before.json').write_text(json.dumps({'guest_swap_configuration': {**config, **change}}))
    with pytest.raises(AssertionError):
        compare.verify_guest_swap_environment(tmp_path)
