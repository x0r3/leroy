"""Bind longer release windows to both completed W Rust qualifications.

Only the supporting Rust qualification is referenced. Full release jobs still
start from fresh application baselines and must execute their original suites.
"""

import hashlib
import zipfile

import nas_release_vm as vm
from nas_original_workload import PHYSICAL_SOURCES
from nas_progress import publish, read_json
from run_nas_full_release_window import require_rust_evidence

CORE = ('src/leroy/actions.py', 'src/leroy/worker.py', 'src/leroy/engine.py',
        'src/leroy/console_logging.py', 'src/leroy/server.py')


def base():
    return vm.ROOT / 'test-results/nas-parity/followup'


def source_binding():
    qualification = base() / 'original-workload-resident-qualification-20261017-w'
    proof = read_json(qualification / 'linux-validation.json')
    assert proof['all_passed'] and proof['native_linux_tests'] == 650 and proof['failures_or_skips'] == 0
    assert vm.digest(qualification / 'inputs.zip') == proof['inputs_sha256']
    with zipfile.ZipFile(qualification / 'inputs.zip') as archive:
        sources = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in (*PHYSICAL_SOURCES, *CORE)}
    assert sources == {name: vm.digest(vm.ROOT / name) for name in sources}
    return {'sources_sha256': sources, 'qualification_sha256': vm.digest(qualification / 'linux-validation.json')}


def validate_engine(engine):
    assert engine in {'leroy', 'jenkins'}
    case = base() / ('acceptance-20261017-w-rust-' + engine)
    window = base() / ('resource-window-acceptance-20261017-w-rust-' + engine)
    result = read_json(window / 'window-result.json')
    assert result['phase'] == 'rust-' + engine and result['outcome'] == 'original_stage_collected'
    assert all(result[k] is True for k in ('original_rust_qualified', 'all_seven_original_services_restored_healthy',
               'healthy_before_deadline', 'native_jenkins_quiet', 'infrastructure_unchanged',
               'controller_process_unchanged', 'controller_no_new_oom'))
    archive = read_json(window / 'closed-disk-archive.json')
    assert archive['source_removed'] and archive['copy_sha256'] == archive['sha256']
    assert not read_json(window / 'restored-window.json').get('host_reserve_stop')
    prepared = read_json(case / 'prepared.json')
    assert prepared['commit'] == vm.COMMIT and prepared['parameters']['CHECK_GROUP'] == 'server-test'
    assert prepared['resource_profile'] == vm.DISK_QOS_FILE_MEMORY_PROFILE
    assert prepared['original_workload_qualification'] and not prepared['synthetic_capacity_qualified']
    assert prepared['matching_ci_background'] and prepared['ci_slots'] == 2
    evidence = require_rust_evidence(case, engine)
    assert evidence['rust']['expected'] == 1657 and evidence['rust']['failed'] == 0
    assert evidence['same_full_rust_test_inventory_as_original'] and evidence['cleanup_complete']
    before = read_json(case / (engine + '-target-before.json'))['manifest']
    assert before == read_json(case / (engine + '-target-after.json'))['manifest']
    assert evidence['identity'] == {'commit': vm.COMMIT, 'runtimeImageId': before['runtimeImageId'],
                                   'sourceSha256': before['files']['verification-source.tar.gz'],
                                   'buildTimestamp': before['build']['timestamp']}
    return {'case': case.name, 'window': window.name, 'original_evidence': evidence,
            'window_sha256': vm.digest(window / 'window-result.json'),
            'archive_sha256': vm.digest(window / 'closed-disk-archive.json')}


def qualify():
    """Create only after validating real successful original archives from both engines."""
    path = base() / 'qualified-rust-reference-20261017-w/qualification.json'
    if path.exists():
        return binding(verify_evidence=True)
    engines = {name: validate_engine(name) for name in ('leroy', 'jenkins')}
    assert engines['leroy']['original_evidence']['identity'] == engines['jenkins']['original_evidence']['identity']
    value = {'commit': vm.COMMIT, 'engines': engines, 'source_binding': source_binding(),
             'supporting_rust_qualification_only': True, 'full_release_results_reused': False,
             'fresh_full_release_baselines_required': True, 'production_ready': False}
    path.parent.mkdir()
    publish(path, value)
    return binding()


def binding(*, verify_evidence=False):
    path = base() / 'qualified-rust-reference-20261017-w/qualification.json'
    proof = read_json(path)
    assert proof['commit'] == vm.COMMIT and proof['supporting_rust_qualification_only'] is True
    assert proof['full_release_results_reused'] is False and proof['fresh_full_release_baselines_required'] is True
    assert set(proof['engines']) == {'leroy', 'jenkins'}
    assert proof['source_binding'] == source_binding()
    for engine, value in proof['engines'].items():
        assert value['original_evidence']['requested_passed'] and value['original_evidence']['cleanup_complete']
        assert value['original_evidence']['rust']['expected'] == 1657 and value['original_evidence']['rust']['failed'] == 0
        if verify_evidence:
            assert value == validate_engine(engine)
    return {'qualification_sha256': vm.digest(path), 'supporting_rust_qualification_only': True,
            'full_release_results_reused': False, 'fresh_full_release_baselines_required': True,
            'original_rust_archives_sha256': {name: value['original_evidence']['archive_sha256']
                                             for name, value in proof['engines'].items()}}


def evidence(engine):
    binding()
    return validate_engine(engine)['original_evidence']
