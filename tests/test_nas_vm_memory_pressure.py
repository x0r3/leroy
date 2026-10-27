"""The reclaim setting must target only the owned VM and preserve hard limits."""

import builtins
import json
import sys
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_vm_memory_pressure as pressure  # noqa: E402


def execute(tmp_path, *, uid=0, running=True, namespace='own-round', engine='jenkins',
            commit=pressure.vm.COMMIT, cgroup=None, high='max', maximum=7 * 1024**3,
            swap_maximum=3 * 1024**3, apply=True, previous=None, expected_max=7*1024**3,
            expected_total=10*1024**3, actual_max=7*1024**3, actual_total=10*1024**3,
            reclaim=pressure.HIGH_BYTES, protected=False, system_max='max'):
    identity = 'a' * 64
    relative = ('/' if protected else '/system.slice/') + 'docker-' + identity + '.scope'
    proc = tmp_path / 'proc' / '71'
    directory = tmp_path / 'cgroup'
    if not protected:
        directory /= 'system.slice'
    directory /= 'docker-' + identity + '.scope'
    proc.mkdir(parents=True)
    directory.mkdir(parents=True)
    proc.joinpath('stat').write_text('71 (qemu) S ' + ' '.join(['0'] * 18 + ['111']))
    proc.joinpath('cgroup').write_text('0::' + (relative if cgroup is None else cgroup) + '\n')
    tmp_path.joinpath('cgroup', 'cgroup.controllers').write_text('memory cpu io\n')
    files = {'memory.high': high, 'memory.low': str(4 * 1024**3 if protected else 0), 'memory.max': str(maximum), 'memory.swap.max': str(swap_maximum),
             'memory.current': '1500000', 'memory.swap.current': '300000',
             'memory.events': 'low 0\nhigh 7\nmax 0\noom 0\noom_kill 0\n'}
    for name, value in files.items():
        directory.joinpath(name).write_text(value + '\n')
    if protected:
        system = tmp_path / 'cgroup/system.slice'
        system.mkdir()
        for name, value in {'memory.max': system_max, 'memory.high': 'max', 'memory.swap.max': 'max',
                            'pids.max': 'max', 'cpu.max': 'max 100000', 'io.max': ''}.items():
            (system / name).write_text(value + '\n')
    info = {'Id': identity, 'State': {'Running': running, 'Pid': 71},
            'Config': {'Labels': {'io.leroy.nas-release-target': commit,
                                 'io.leroy.comparison': namespace, 'io.leroy.engine': engine}},
            'HostConfig': {'Memory': actual_max, 'MemorySwap': actual_total,
                           'CgroupParent': '-.slice' if protected else 'system.slice',
                           'MemoryReservation': 4 * 1024**3 if protected else 0}}

    def mapped(path):
        value = PurePosixPath(path)
        if value.parts[:2] == ('/', 'proc'):
            return tmp_path.joinpath('proc', *value.parts[2:])
        if str(value) == '/sys/fs/cgroup':
            return tmp_path / 'cgroup'
        if protected and str(value) == '/sys/fs/cgroup/system.slice':
            return tmp_path / 'cgroup/system.slice'
        pytest.fail('Unexpected host path: ' + str(value))

    def inspect(command, *, text, timeout):
        assert command == ['docker', 'inspect', pressure.vm.CONTAINER] and text and timeout == 15
        return json.dumps([info])

    descriptors = {}

    def open_parameter(path, flags):
        assert path == directory / 'memory.high' and flags == 1 | 2048 | 131072
        descriptors[1] = path.open('wb')
        return 1

    def write_parameter(descriptor, data):
        assert descriptor == 1
        result = descriptors[descriptor].write(data)
        descriptors[descriptor].flush()
        return result

    modules = {'json': json, 'os': SimpleNamespace(geteuid=lambda: uid, open=open_parameter,
               write=write_parameter, close=lambda descriptor: descriptors.pop(descriptor).close(),
               O_WRONLY=1, O_NONBLOCK=2048, O_NOFOLLOW=131072),
               'pathlib': SimpleNamespace(Path=mapped, PurePosixPath=PurePosixPath),
               'subprocess': SimpleNamespace(check_output=inspect)}
    output = []
    environment = {**vars(builtins), '__import__': lambda name, *args: modules[name], 'print': output.append}
    globals_ = {'__builtins__': environment, 'CONTAINER': pressure.vm.CONTAINER, 'COMMIT': pressure.vm.COMMIT,
                'ROUND': 'own-round', 'ENGINE': 'jenkins', 'HIGH': reclaim,
                'EXPECTED_MAX':expected_max,'EXPECTED_TOTAL':expected_total,
                'APPLY': apply, 'PREVIOUS': previous, 'PROTECTED': protected}
    try:
        exec(pressure.PROGRAM, globals_)
    finally:
        if not output:
            assert directory.joinpath('memory.high').read_text().strip() == high
    return json.loads(output[0]), directory


@pytest.mark.parametrize('options', [
    {'uid': 1000}, {'running': False}, {'namespace': 'foreign-round'}, {'engine': 'leroy'},
    {'commit': 'b' * 40}, {'cgroup': '/'}, {'cgroup': '/docker/foreign'},
    {'cgroup': '/docker/../foreign'}, {'high': '1000'}, {'maximum': 6 * 1024**3}, {'swap_maximum': 0},
])
def test_unowned_target_or_unexpected_hard_limits_are_never_changed(tmp_path, options):
    with pytest.raises(AssertionError):
        execute(tmp_path, **options)


def test_only_owned_reclaim_threshold_changes(tmp_path):
    result, directory = execute(tmp_path)
    assert directory.joinpath('memory.high').read_text() == str(pressure.HIGH_BYTES) + '\n'
    assert result['original_memory_high'] == 'max'
    assert result['memory_max_bytes'] == 7 * 1024**3 and result['memory_swap_max_bytes'] == 3 * 1024**3
    assert result['events']['high'] == 7 and result['events']['oom_kill'] == 0
    assert not result['guest_capacity_changed'] and not result['global_host_kernel_settings_changed']


@pytest.mark.parametrize('system_max', ['max', str(6 * 1024**3)])
def test_private_root_scope_protects_working_set_without_bypassing_system_limits(tmp_path, system_max):
    options = {'protected': True, 'system_max': system_max, 'maximum': 9 * 1024**3,
               'swap_maximum': 4 * 1024**3, 'expected_max': 9 * 1024**3,
               'expected_total': 13 * 1024**3, 'actual_max': 9 * 1024**3,
               'actual_total': 13 * 1024**3, 'reclaim': 5 * 1024**3}
    if system_max != 'max':
        with pytest.raises(AssertionError, match='Never bypass'):
            execute(tmp_path, **options)
    else:
        result, _ = execute(tmp_path, **options)
        assert result['memory_low_bytes'] == 4 * 1024**3
        assert result['memory_high_bytes'] == 5 * 1024**3
        assert result['cgroup_parent'] == '-.slice'


def test_read_only_observation_does_not_reapply_settings(tmp_path):
    result, directory = execute(tmp_path, high=str(pressure.HIGH_BYTES), apply=False)
    assert directory.joinpath('memory.high').read_text() == str(pressure.HIGH_BYTES) + '\n'
    assert result['memory_high_bytes'] == pressure.HIGH_BYTES


@pytest.mark.parametrize('previous', [
    {'container_id': 'b' * 64, 'process_start_ticks': '111', 'original_memory_high': 'max'},
    {'container_id': 'a' * 64, 'process_start_ticks': '999', 'original_memory_high': 'max'},
])
def test_restart_identity_mismatch_prevents_reapplication(tmp_path, previous):
    with pytest.raises(AssertionError):
        execute(tmp_path, high=str(pressure.HIGH_BYTES), previous=previous)


def test_same_container_resume_preserves_original_marker(tmp_path):
    previous = {'container_id': 'a' * 64, 'process_start_ticks': '111', 'original_memory_high': 'max'}
    result, _ = execute(tmp_path, high=str(pressure.HIGH_BYTES), previous=previous)
    assert result['original_memory_high'] == 'max'


def test_correctly_sized_guest_changes_only_its_reclaim_threshold(tmp_path):
    result,directory=execute(tmp_path,maximum=11*1024**3,swap_maximum=4*1024**3,
        expected_max=11*1024**3,expected_total=15*1024**3,
        actual_max=11*1024**3,actual_total=15*1024**3,reclaim=4*1024**3)
    assert result['memory_max_bytes']==11*1024**3
    assert result['memory_swap_max_bytes']==4*1024**3
    assert directory.joinpath('memory.high').read_text().strip()==str(4*1024**3)


def test_new_budget_does_not_accept_old_or_unknown_container_limits(tmp_path):
    with pytest.raises(AssertionError):
        execute(tmp_path,expected_max=11*1024**3,expected_total=15*1024**3)


def test_eight_gib_guest_keeps_four_gib_outer_swap_and_validates_actual_limits(tmp_path):
    result, _ = execute(tmp_path, maximum=9*1024**3, swap_maximum=4*1024**3,
        expected_max=9*1024**3, expected_total=13*1024**3,
        actual_max=9*1024**3, actual_total=13*1024**3, reclaim=3584*1024**2)
    assert result['memory_max_bytes'] == 9*1024**3 and result['memory_swap_max_bytes'] == 4*1024**3


@pytest.mark.parametrize('profile', ['nas-6g-ssd-fine-pages', 'nas-6g-ssd-soft-ram', 'nas-6g-ssd-soft-ram-3328', 'nas-6g-ssd-soft-ram-3584'])
def test_new_profile_preserves_guest_capacity_io_and_hard_limits(monkeypatch, profile):
    attributes = ('ROUND', 'RESOURCE_PROFILE', 'GUEST_MEMORY_MB', 'CONTAINER_MEMORY_GIB',
                  'CONTAINER_MEMORY_SWAP_GIB', 'VM_IO_LIMITS', 'BASELINE_ROOT', 'DISK_ROOT',
                  'LAUNCHER', 'MIN_DISK_FREE_MB')
    for name in attributes:
        monkeypatch.setattr(pressure.vm, name, getattr(pressure.vm, name))
    monkeypatch.setattr(pressure.vm, 'ROUND', None)
    pressure.vm.configure('own-round', profile)
    assert pressure.vm.GUEST_MEMORY_MB == 6144
    assert pressure.vm.CONTAINER_MEMORY_GIB == 7 and pressure.vm.CONTAINER_MEMORY_SWAP_GIB == 10
    assert pressure.vm.VM_IO_LIMITS['read_bps'] == 128 * 1024**2
    assert pressure.vm.VM_IO_LIMITS['write_bps'] == 32 * 1024**2
    assert pressure.vm.MIN_DISK_FREE_MB == 40 * 1024
    assert pressure.vm.MIN_HOST_AVAILABLE_MB == 128 and pressure.vm.MIN_HOST_SWAP_MB == 2304
    assert profile in pressure.vm.PAGE_REPORTING_PROFILES and profile in pressure.vm.PROACTIVE_CACHE_PROFILES


@pytest.mark.parametrize('profile,high,guest,maximum,total',[
    ('nas-10g-ssd-soft-ram-4096',4*1024**3,10240,11,15),
    ('nas-10g-ssd-soft-ram-3584',3584*1024**2,10240,11,15),
    ('nas-8g-ssd-soft-ram-3584',3584*1024**2,8192,9,13),
    ('nas-8g-ssd-soft-ram-3840',3840*1024**2,8192,9,13),
    ('nas-8g-ssd-soft-ram-4096',4096*1024**2,8192,9,13)])
def test_builder_capacity_profile_is_explicit_and_preserves_nas_safety(monkeypatch,profile,high,guest,maximum,total):
    attributes = ('ROUND', 'RESOURCE_PROFILE', 'GUEST_MEMORY_MB', 'CONTAINER_MEMORY_GIB',
                  'CONTAINER_MEMORY_SWAP_GIB', 'VM_IO_LIMITS', 'BASELINE_ROOT', 'DISK_ROOT',
                  'LAUNCHER', 'MIN_DISK_FREE_MB')
    for name in attributes:
        monkeypatch.setattr(pressure.vm, name, getattr(pressure.vm, name))
    monkeypatch.setattr(pressure.vm, 'ROUND', None)
    pressure.vm.configure('own-round', profile)
    assert pressure.vm.GUEST_MEMORY_MB == guest
    assert (pressure.vm.CONTAINER_MEMORY_GIB, pressure.vm.CONTAINER_MEMORY_SWAP_GIB) == (maximum, total)
    assert pressure.vm.MIN_HOST_AVAILABLE_MB == 128 and pressure.vm.MIN_HOST_SWAP_MB == 2304
    assert pressure.vm.MIN_DISK_FREE_MB == 40*1024
    assert pressure.vm.VM_IO_LIMITS['read_bps'] == 128*1024**2
    assert pressure.vm.VM_IO_LIMITS['write_bps'] == 32*1024**2
    assert pressure.high_bytes_for_profile(pressure.vm.RESOURCE_PROFILE) == high


@pytest.mark.parametrize('profile,expected', [('nas-6g-ssd-soft-ram', 3 * 1024**3),
    ('nas-6g-ssd-soft-ram-3328', 3328 * 1024**2), ('nas-6g-ssd-soft-ram-3584', 3584 * 1024**2)])
def test_memory_profile_selects_its_pinned_threshold(monkeypatch, profile, expected):
    monkeypatch.setattr(pressure.vm, 'ROUND', 'own-round')
    monkeypatch.setattr(pressure.vm, 'RESOURCE_PROFILE', profile)
    def remote(program, *, sudo, timeout):
        assert sudo and timeout == 45
        assert '\nHIGH=' + repr(expected) + '\n' in program
        return json.dumps({'memory_high_bytes': expected})
    monkeypatch.setattr(pressure.vm, 'remote', remote)
    assert pressure.observe_outer_memory_pressure('jenkins')['memory_high_bytes'] == expected


def test_unconfigured_memory_profile_fails_before_remote_operation(monkeypatch):
    monkeypatch.setattr(pressure.vm, 'ROUND', 'own-round')
    monkeypatch.setattr(pressure.vm, 'RESOURCE_PROFILE', 'nas-4g5')
    monkeypatch.setattr(pressure.vm, 'remote', lambda *args, **kwargs: pytest.fail('No remote call for unsupported profile'))
    with pytest.raises(AssertionError):
        pressure.observe_outer_memory_pressure('leroy')


def test_disk_only_qos_keeps_capacity_and_nas_reserves(monkeypatch):
    for name in ('ROUND', 'RESOURCE_PROFILE', 'GUEST_MEMORY_MB', 'CONTAINER_MEMORY_GIB',
                 'CONTAINER_MEMORY_SWAP_GIB', 'VM_IO_LIMITS', 'BASELINE_ROOT', 'DISK_ROOT',
                 'LAUNCHER', 'MIN_DISK_FREE_MB', 'DISK_CACHE'):
        monkeypatch.setattr(pressure.vm, name, getattr(pressure.vm, name))
    monkeypatch.setattr(pressure.vm, 'ROUND', None)
    pressure.vm.configure('own-disk-qos', pressure.vm.DISK_QOS_FILE_MEMORY_PROFILE)
    assert pressure.vm.GUEST_MEMORY_MB == 7168
    assert (pressure.vm.CONTAINER_MEMORY_GIB, pressure.vm.CONTAINER_MEMORY_SWAP_GIB) == (9, 13)
    assert pressure.vm.VM_IO_LIMITS['target'] == 'qemu-disk'
    assert pressure.vm.VM_IO_LIMITS['read_bps'] == 128 * 1024**2
    assert pressure.vm.VM_IO_LIMITS['write_bps'] == 32 * 1024**2
    assert pressure.vm.DISK_CACHE == 'none' and pressure.vm.LAUNCHER.endswith('/file-memory-v2/launch.py')
    assert pressure.high_bytes_for_profile(pressure.vm.RESOURCE_PROFILE) == 5 * 1024**3
    assert pressure.vm.MIN_HOST_AVAILABLE_MB == 128 and pressure.vm.MIN_HOST_SWAP_MB == 2304
