"""Permit the Jenkins counterpart of failed W; never qualify a release from it."""

import nas_release_vm as vm
from nas_progress import read_json
from nas_rust_reference import base, source_binding

RUN = 'f4af042f894b422bbeda50a8b07c8d98'
BACKEND_RUN = 'd64afdbb7dfb4a69bc464edc238b707f'


def validate(data):
    run, window, archive = (data[k] for k in ('run', 'window', 'archive'))
    assert run['id'] == RUN and run['number'] == 186
    assert run['status'] == 'failed' and run['cancel_requested'] is False
    assert run['reason'] == 'verify: Process exited with code 1'
    assert run['commit'] == vm.COMMIT and run['parameters']['CHECK_GROUP'] == 'server-test'
    assert run['snapshot']['source']['application_patches_applied'] is False
    assert window['phase'] == 'rust-leroy' and window['original_rust_qualified'] is False
    assert window['outcome'] == 'stopped:AssertionError'
    assert all(window[k] is True for k in ('all_seven_original_services_restored_healthy',
               'healthy_before_deadline', 'native_jenkins_quiet', 'infrastructure_unchanged',
               'controller_process_unchanged', 'controller_no_new_oom'))
    assert archive['source_removed'] and archive['copy_sha256'] == archive['sha256']
    assert data['restored']['phase'] == 'restored' and not data['restored'].get('host_reserve_stop')
    assert data['memory']['released_after_vm_stopped'] is True
    prepared = data['prepared']
    assert prepared['commit'] == vm.COMMIT and prepared['parameters']['CHECK_GROUP'] == 'server-test'
    assert prepared['resource_profile'] == vm.DISK_QOS_FILE_MEMORY_PROFILE
    assert prepared['original_workload_qualification'] and not prepared['synthetic_capacity_qualified']
    assert prepared['matching_ci_background'] and prepared['ci_slots'] == 2
    manifest, receipt = data['target']['manifest'], data['receipt']
    assert manifest['commit'] == vm.COMMIT
    assert receipt['commit'] == vm.COMMIT and receipt['requestedGroup'] == 'server-test'
    assert receipt['runId'] == BACKEND_RUN
    assert receipt['runtimeImageId'] == manifest['runtimeImageId']
    assert receipt['sourceSha256'] == manifest['files']['verification-source.tar.gz']
    assert receipt['buildTimestamp'] == manifest['build']['timestamp']
    assert receipt['activeRelease'] and receipt['cleanupComplete'] and not receipt['cancelled']
    assert receipt['requestedPassed'] is False and receipt['checks']['server-test']['passed'] is False
    tests = data['rust']
    assert tests['expectedTests'] == tests['measuredTests'] == 0 and tests['complete'] is False
    return {'diagnostic_reference_only': True, 'failed_original_run_id': RUN, 'failed_original_number': 186,
            'source_commit': vm.COMMIT, 'original_ci_results_reused': False,
            'offline_receipt_is_original_ci_artifact': False,
            'full_release_still_requires_both_successful_original_rust_runs': True,
            'synthetic_capacity_qualified': False, 'production_ready': False}


def binding():
    case = base() / 'acceptance-20261017-w-rust-leroy'
    window = base() / 'resource-window-acceptance-20261017-w-rust-leroy'
    paths = {'run': case / 'leroy-run.json', 'prepared': case / 'prepared.json',
             'target': case / 'leroy-target-before.json', 'memory': case / 'leroy-file-memory-released.json',
             'receipt': case / 'offline-quality-leroy/result.json',
             'rust': case / 'offline-quality-leroy/rust-test-times.json',
             'window': window / 'window-result.json', 'archive': window / 'closed-disk-archive.json',
             'restored': window / 'restored-window.json'}
    value = validate({key: read_json(path) for key, path in paths.items()})
    value['source_binding'] = source_binding()
    value['source_evidence_sha256'] = {p.relative_to(base()).as_posix(): vm.digest(p) for p in paths.values()}
    return value
