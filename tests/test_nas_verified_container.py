"""A slow Docker API must not turn a verified observation into a new target."""

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_followup_support as support  # noqa: E402
import nas_release_vm as vm  # noqa: E402
from nas_verified_container import HELPERS, discover_program, verify_program  # noqa: E402


@pytest.fixture
def verified(monkeypatch, tmp_path):
    cid = 'a' * 64
    process = {'start_ticks': '100', 'cgroup': '0::/docker-' + cid + '.scope\n',
               'command_sha256': 'b' * 64, 'namespaces': {'mnt': 'mnt:[2]', 'net': 'net:[3]', 'pid': 'pid:[4]'}}
    mount = tmp_path / 'home'
    mount.mkdir()
    inode = {'device': mount.stat().st_dev, 'inode': mount.stat().st_ino}
    pin = {'container_id': cid, 'pid': 42, 'boot_id': 'boot', 'process': copy.deepcopy(process),
           'mounts': {'/var/jenkins_home': {'source': str(mount), 'directory': dict(inode)}}, 'labels': {}}
    namespace = {}
    exec(HELPERS, namespace)
    original = Path.read_text
    monkeypatch.setattr(Path, 'read_text', lambda p, *a, **kw: 'boot\n' if p.as_posix() == '/proc/sys/kernel/random/boot_id' else original(p, *a, **kw))
    namespace['process_identity'] = lambda pid: copy.deepcopy(process)
    namespace['directory_identity'] = lambda path: dict(inode)
    return pin, process, inode, namespace


def test_verified_process_and_mount_need_no_docker_rpc(verified):
    pin, _, _, namespace = verified
    assert namespace['verify_pin'](pin) is pin
    assert 'docker' not in verify_program(pin).replace('docker-', '')


@pytest.mark.parametrize('field,value', [
    ('start_ticks', '101'), ('command_sha256', 'c' * 64), ('cgroup', '0::/other\n'),
    ('namespaces', {'mnt': 'mnt:[999]', 'net': 'net:[3]', 'pid': 'pid:[4]'}),
])
def test_pid_reuse_exec_cgroup_or_namespace_change_is_rejected(verified, field, value):
    pin, process, _, namespace = verified
    process[field] = value
    with pytest.raises(AssertionError, match='process changed'):
        namespace['verify_pin'](pin)


def test_boot_and_mount_replacement_are_rejected(verified):
    pin, _, inode, namespace = verified
    pin['boot_id'] = 'another-boot'
    with pytest.raises(AssertionError):
        namespace['verify_pin'](pin)
    pin['boot_id'] = 'boot'
    inode['inode'] += 1
    with pytest.raises(AssertionError, match='mount source replaced'):
        namespace['verify_pin'](pin)


def test_discovery_is_name_and_label_bound_and_bounded():
    code = discover_program('leroy-nas-release-target-vm', labels={'io.leroy.comparison': 'owned-round'},
                            retained_labels=('io.leroy.engine',))
    compile(code, '<discovery>', 'exec')
    assert "timeout=20" in code and "info['Name']=='/'+NAME" in code
    assert "EXPECTED_LABELS.items()" in code and "RETAIN_LABELS" in code
    with pytest.raises(AssertionError):
        discover_program('unrelated')


def test_production_prelude_discovers_once_and_checks_each_observation(monkeypatch):
    pin = {'mounts': {'/var/jenkins_home': {'source': '/data/jenkins'}}}
    calls = []

    def run(program, *args, **kwargs):
        calls.append(program)
        return SimpleNamespace(returncode=0, stdout=json.dumps(pin), stderr='')

    monkeypatch.setattr(support, '_PRODUCTION_PIN', None)
    monkeypatch.setattr(support, 'run_script', run)
    first = support.production_prelude()
    assert support.production_prelude() == first and len(calls) == 1
    assert 'verify_pin(PIN)' in first
    assert "subprocess.check_output(['docker','inspect'" not in first


def test_guest_never_rediscovers_after_a_pinned_process_changes(monkeypatch):
    pin = {'labels': {'io.leroy.engine': 'leroy'}, 'pid': 42}
    calls = []

    def remote(program, *args, **kwargs):
        calls.append(program)
        if len(calls) == 1:
            return json.dumps(pin)
        raise RuntimeError('Pinned process changed')

    monkeypatch.setattr(vm, '_GUEST_PIN', None)
    monkeypatch.setattr(vm, 'remote', remote)
    for _ in range(2):
        with pytest.raises(RuntimeError, match='Pinned process changed'):
            vm.guest('true')
    assert len(calls) == 3
    assert sum("subprocess.check_output(['docker','inspect'" in code for code in calls) == 1
