"""Future release time budgets cannot turn incomplete Rust evidence into success."""

import copy
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_rust_reference as rust  # noqa: E402


@pytest.fixture
def original(tmp_path, monkeypatch):
    monkeypatch.setattr(rust.vm, 'ROOT', tmp_path)
    case = rust.base() / 'acceptance-20261017-w-rust-leroy'
    window = rust.base() / 'resource-window-acceptance-20261017-w-rust-leroy'
    case.mkdir(parents=True)
    window.mkdir()
    receipt = {'requested_passed': True, 'cleanup_complete': True,
               'same_full_rust_test_inventory_as_original': True, 'rust': {'expected': 1657, 'failed': 0},
               'archive_sha256': 'a' * 64, 'identity': {'commit': rust.vm.COMMIT,
               'runtimeImageId': 'runtime', 'sourceSha256': 'source', 'buildTimestamp': 'stamp'}}
    monkeypatch.setattr(rust, 'require_rust_evidence', lambda *_: copy.deepcopy(receipt))
    files = {window / 'window-result.json': {'phase': 'rust-leroy', 'outcome': 'original_stage_collected',
              **{name: True for name in ('original_rust_qualified', 'all_seven_original_services_restored_healthy',
                   'healthy_before_deadline', 'native_jenkins_quiet', 'infrastructure_unchanged',
                   'controller_process_unchanged', 'controller_no_new_oom')}},
             window / 'closed-disk-archive.json': {'source_removed': True, 'copy_sha256': 'same', 'sha256': 'same'},
             window / 'restored-window.json': {'host_reserve_stop': False},
             case / 'prepared.json': {'commit': rust.vm.COMMIT, 'parameters': {'CHECK_GROUP': 'server-test'},
                  'resource_profile': rust.vm.DISK_QOS_FILE_MEMORY_PROFILE, 'original_workload_qualification': True,
                  'synthetic_capacity_qualified': False, 'matching_ci_background': True, 'ci_slots': 2}}
    manifest = {'runtimeImageId': 'runtime', 'files': {'verification-source.tar.gz': 'source'}, 'build': {'timestamp': 'stamp'}}
    for boundary in ('before', 'after'):
        files[case / ('leroy-target-' + boundary + '.json')] = {'manifest': copy.deepcopy(manifest)}
    for path, value in files.items():
        path.write_text(json.dumps(value))
    return case, window, receipt


def test_complete_qualified_archive_can_be_a_supporting_reference(original):
    value = rust.validate_engine('leroy')
    assert value['original_evidence']['rust']['expected'] == 1657
    assert value['original_evidence']['archive_sha256'] == 'a' * 64


@pytest.mark.parametrize('file,key,value', [
    ('window-result.json', 'original_rust_qualified', False),
    ('window-result.json', 'healthy_before_deadline', False),
    ('window-result.json', 'native_jenkins_quiet', False),
    ('closed-disk-archive.json', 'copy_sha256', 'different'),
    ('restored-window.json', 'host_reserve_stop', True),
])
def test_failed_or_unclosed_window_cannot_qualify_release(original, file, key, value):
    _, window, _ = original
    path = window / file
    state = json.loads(path.read_text())
    state[key] = value
    path.write_text(json.dumps(state))
    with pytest.raises(AssertionError):
        rust.validate_engine('leroy')


def test_partial_inventory_and_changed_runtime_are_rejected(original):
    _, _, receipt = original
    receipt['rust']['expected'] = 1656
    with pytest.raises(AssertionError):
        rust.validate_engine('leroy')
    receipt['rust']['expected'] = 1657
    receipt['identity']['runtimeImageId'] = 'other-build-of-same-commit'
    with pytest.raises(AssertionError):
        rust.validate_engine('leroy')


def test_one_success_never_writes_a_two_engine_qualification(original, monkeypatch):
    def only_one(engine):
        if engine == 'jenkins':
            raise AssertionError('Original Jenkins archive missing')
        return {'original_evidence': {'identity': {}}}
    monkeypatch.setattr(rust, 'validate_engine', only_one)
    with pytest.raises(AssertionError, match='Jenkins archive missing'):
        rust.qualify()
    assert not (rust.base() / 'qualified-rust-reference-20261017-w').exists()


def test_changed_execution_source_invalidates_previous_rust_qualification(tmp_path, monkeypatch):
    monkeypatch.setattr(rust.vm, 'ROOT', tmp_path)
    monkeypatch.setattr(rust, 'PHYSICAL_SOURCES', ('physical.py',))
    monkeypatch.setattr(rust, 'CORE', ('core.py',))
    q = rust.base() / 'original-workload-resident-qualification-20261017-w'
    q.mkdir(parents=True)
    for name in ('physical.py', 'core.py'):
        (tmp_path / name).write_text('unchanged')
    with zipfile.ZipFile(q / 'inputs.zip', 'w') as archive:
        for name in ('physical.py', 'core.py'):
            archive.write(tmp_path / name, name)
    (q / 'linux-validation.json').write_text(json.dumps({'all_passed': True, 'native_linux_tests': 650,
        'failures_or_skips': 0, 'inputs_sha256': rust.vm.digest(q / 'inputs.zip')}))
    assert rust.source_binding()['sources_sha256']['core.py']
    (tmp_path / 'core.py').write_text('changed worker semantics')
    with pytest.raises(AssertionError):
        rust.source_binding()
