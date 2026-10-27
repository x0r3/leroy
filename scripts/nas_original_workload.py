"""Qualify through unchanged original jobs; never turn failed stress into success."""
import json
import time
import zipfile

import nas_release_vm as vm

REFERENCE = 'day-o-rust-leroy-20261015'
PHYSICAL_SOURCES = ('scripts/nas_release_vm.py', 'infra/vm/launch.py', 'scripts/nas_vm_memory_pressure.py',
                    'scripts/nas_vm_guest_swap.py', 'scripts/nas_vm_page_reporting.py', 'infra/vm/graphato-lifecycle.py',
                    'scripts/deploy_nas_engine_memory.py', 'scripts/deploy_nas_control_working_set.py')
QUALIFIED_SOURCES = ('scripts/nas_original_workload.py', 'scripts/compare_nas_full_release.py',
                     'scripts/diagnose_nas_release_group.py', 'scripts/nas_vm_file_memory.py',
                     'scripts/run_nas_day_window.py', 'scripts/nas_resource_window_guard.py')


def read(path):
    from nas_progress import read_json

    return read_json(path)


def resource_ast(data):
    """Only the SSH result classifier may differ from the retained physical profile."""
    import ast

    module = ast.parse(data)
    module.body = [n for n in module.body if not isinstance(n, ast.FunctionDef) or n.name != 'ssh_transport_unavailable']
    return ast.dump(module, include_attributes=False)


def binding(profile, *, diagnostic_reference=False, upstream_transport=False, guest_dns=False, resident=False, resident_attempt='v'):
    assert not (diagnostic_reference and upstream_transport)
    assert not guest_dns or upstream_transport
    assert profile == vm.DISK_QOS_FILE_MEMORY_PROFILE
    base = vm.ROOT / 'test-results/nas-parity/followup'
    case = base / REFERENCE
    window = base / 'resource-window-day-20261015-o-rust-leroy'
    plan = read(base / 'day-window-plan-20261015-o-rust-leroy/approval.json')
    result = read(window / 'window-result.json')
    assert all(result[k] is True for k in ('all_seven_original_services_restored_healthy', 'native_jenkins_quiet',
               'infrastructure_unchanged', 'controller_process_unchanged', 'controller_no_new_oom'))
    assert result['original_rust_qualified'] is False and not (case / 'leroy-start.json').exists()
    archive = read(window / 'closed-disk-archive.json')
    assert archive['source_removed'] and archive['copy_sha256'] == archive['sha256']
    assert not read(window / 'restored-window.json').get('host_reserve_stop')
    memory = read(case / 'leroy-memory-summary.json')
    assert memory['minimum_host_available_kib'] >= vm.MIN_HOST_AVAILABLE_MB * 1024
    assert memory['minimum_host_swap_free_kib'] >= vm.MIN_HOST_SWAP_MB * 1024
    assert plan['source_commit'] == vm.COMMIT and plan['resource_profile'] == profile
    sources = {name: vm.digest(vm.ROOT / name) for name in PHYSICAL_SOURCES}
    for name, sha in sources.items():
        if resident and name == 'scripts/nas_release_vm.py':
            retained = base / 'day-window-plan-20261015-o-rust-leroy/approved-sources' / name
            assert vm.digest(retained) == plan['script_sha256'][name]
            assert resource_ast(retained.read_bytes()) == resource_ast((vm.ROOT / name).read_bytes())
        else:
            assert plan['script_sha256'][name] == sha
    log = case / 'offline-capacity-forensics/agent.jsonl'
    assert b'TimeoutError: timed out' in log.read_bytes()
    assert not (case / 'leroy-file-memory-capacity.json').exists()
    files = [window / name for name in ('window-result.json', 'closed-disk-archive.json', 'restored-window.json')]
    files += [log, case / 'nas-capacity-retained-evidence.json', case / 'leroy-memory-summary.json']
    qualification = base / ('original-workload-resident-qualification-20261017' + ('-' + resident_attempt if resident_attempt in {'w', 'x', 'y'} else '') if resident else
                            'original-workload-dns-qualification-20261016-b' if guest_dns else
                            'original-workload-upstream-qualification-20261016-c' if upstream_transport else
                            'original-workload-reference-qualification-20261016' if diagnostic_reference else
                            'original-workload-qualification-20261015')
    linux = read(qualification / 'linux-validation.json')
    assert linux['all_passed'] is True
    assert (linux['native_linux_tests'] >= 100 if resident else
            linux['native_linux_tests'] == (82 if guest_dns else 54 if upstream_transport else 38 if diagnostic_reference else 19))
    if resident:
        assert linux['nas_native_runtime_qualified'] is True and linux['original_ci_dispatched'] is False
    assert linux['failures_or_skips'] == 0
    assert linux['vm_started'] is linux['memory_load_started'] is linux['guest_ssh_requests'] is False
    bundle = qualification / 'inputs.zip'
    assert vm.digest(bundle) == linux['inputs_sha256']
    with zipfile.ZipFile(bundle) as archive:
        import hashlib

        assert all(hashlib.sha256(archive.read(name)).hexdigest() == vm.digest(vm.ROOT / name)
                   for name in QUALIFIED_SOURCES)
        if upstream_transport:
            assert all(hashlib.sha256(archive.read(name)).hexdigest() == vm.digest(vm.ROOT / name)
                       for name in ('scripts/nas_graphato_transport.py', 'scripts/run_nas_capacity_window.py'))
        if guest_dns:
            assert all(hashlib.sha256(archive.read(name)).hexdigest() == vm.digest(vm.ROOT / name) for name in
                       ('scripts/nas_vm_dns.py', 'scripts/nas_progress.py', 'scripts/run_nas_night_window.py',
                        'scripts/compare_frozen_postdeploy_group.py'))
        if resident:
            assert all(hashlib.sha256(archive.read(name)).hexdigest() == vm.digest(vm.ROOT / name) for name in
                       ('scripts/nas_native.py', 'scripts/nas_ssh.py', 'scripts/nas_open_authorization.py',
                        'scripts/nas_acceptance_service.py', 'scripts/nas_lease_recorder.py', 'scripts/nas_source_git.py'))
    return {'negative_supplemental_stress_case': REFERENCE,
            'negative_evidence_sha256': {p.relative_to(base).as_posix(): vm.digest(p) for p in files},
            'physical_sources_sha256': sources, 'resource_profile': profile,
            'synthetic_capacity_qualified': False, 'original_ci_results_reused': False,
            'complete_original_job_required': True, 'fresh_application_baseline_required': True,
            'linux_gate_validation_sha256': vm.digest(qualification / 'linux-validation.json')}


def validate_failed_reference(data, physical_sources):
    """A terminal failed original job allows diagnosis, never a release waiver."""
    run, window, archive = (data[k] for k in ('run', 'window', 'archive'))
    assert run['id'] == 'e32366e7ffb249a4b7753d00ff6bd4c6' and run['number'] == 179
    assert run['status'] == 'failed' and run['reason'] == 'verify: Process exited with code 1'
    assert run['commit'] == vm.COMMIT and run['cancel_requested'] is False
    assert run['parameters']['CHECK_GROUP'] == 'server-test'
    assert run['snapshot']['source']['application_patches_applied'] is False
    assert window['original_ci_terminal'] is True and window['original_rust_qualified'] is False
    assert window['vm_running'] is False and window['restored_before_deadline'] is True
    assert all(window[k] is True for k in ('all_seven_original_services_restored_healthy',
               'infrastructure_unchanged', 'controller_process_unchanged', 'controller_no_new_oom'))
    assert window['healthy_before_deadline'] is False
    assert window['health_verification_was_delayed_by_lost_administrative_access'] is True
    assert data['production']['native_jenkins_quiet_during_window_verified'] is True
    assert data['production']['changed_build_overlaps_test_window'] is False
    assert data['production']['production_modified'] is False
    assert archive['source_removed'] and archive['sha256'] == archive['copy_sha256']
    assert data['restored']['phase'] == 'restored' and not data['restored'].get('host_reserve_stop')
    assert data['plan']['source_commit'] == vm.COMMIT
    assert data['plan']['resource_profile'] == vm.DISK_QOS_FILE_MEMORY_PROFILE
    assert all(data['plan']['script_sha256'][name] == sha for name, sha in physical_sources.items())
    assert data['memory']['aligned_guest_host_samples'] > 0
    assert data['memory']['minimum_host_available_kib'] >= vm.MIN_HOST_AVAILABLE_MB * 1024
    assert data['memory']['minimum_host_swap_free_kib'] >= vm.MIN_HOST_SWAP_MB * 1024
    target = data['target']
    assert target['manifest']['commit'] == vm.COMMIT
    assert target['manifest']['runtimeImageId'] == 'sha256:6251c60f499e41e706613f931bf281ce52312b957d5a6a123cf4e27dd3242585'
    assert target['manifest']['files']['verification-source.tar.gz'] == 'f0c737a8133cd73f6b34c66be5081316a7047a1881583532874b40abaec59708'
    assert len(target['containers']) == 4 and all(row['health'] == 'healthy' for row in target['containers'])
    receipt = data['receipt']
    assert receipt['commit'] == vm.COMMIT and receipt['requestedGroup'] == 'server-test'
    assert receipt['runId'] == 'd26c4c6fe1b54e4f8ca56f293d190ced'
    assert receipt['runtimeImageId'] == target['manifest']['runtimeImageId']
    assert receipt['sourceSha256'] == target['manifest']['files']['verification-source.tar.gz']
    assert receipt['cancelled'] is False and receipt['cleanupComplete'] is True
    assert receipt['checks']['server-test']['errorType'] == 'TimeoutExpired' and receipt['requestedPassed'] is False
    return {'diagnostic_reference_only': True, 'failed_original_run_id': run['id'], 'failed_original_number': 179,
            'source_commit': vm.COMMIT, 'physical_sources_sha256': physical_sources,
            'prior_health_before_deadline_verified': False, 'late_health_and_native_boundary_resolution_retained': True,
            'original_ci_results_reused': False, 'full_release_still_requires_both_successful_original_rust_runs': True,
            'synthetic_capacity_qualified': False, 'production_ready': False}


def validate_scope(value, case, engine):
    assert engine in {'leroy', 'jenkins'} and value['attempt'] in {'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'}
    attempt = value['attempt']
    phase = value['phase']
    assert phase in ('rust-' + engine, 'release-' + engine)
    if attempt in {'v', 'w', 'x', 'y'}:
        import run_nas_day_window as day

        assert case == day.round_name(phase, attempt) and value['window'] == day.window_name(phase, attempt)
    else:
        assert case == ('day-' + attempt + '-rust-' + engine + '-20261015' if phase.startswith('rust-') else 'day-' + attempt + '-release-20261015')
        assert value['window'] == 'resource-window-day-20261015-' + attempt + '-' + phase
    assert value['comparison_rounds'] == [case] and value['engine'] == engine
    assert value['source_commit'] == vm.COMMIT and value['resource_profile'] == vm.DISK_QOS_FILE_MEMORY_PROFILE
    assert value['original_workload_qualification'] is True and value['matching_ci_background'] is True
    assert value.get('nas_local_capacity', False) is False and not value.get('separate_capacity_reference')
    assert value['ci_slots'] == 2 and value['application_sources_tests_and_fixture_limits_unchanged'] is True
    assert value['maximum_window_seconds'] == (43200 if attempt == 'x' else 14400) and value['restore_margin_seconds'] == 900
    assert value['production_cutover'] is False and value['host_swap_and_kernel_settings_changed'] is False
    if attempt in {'t', 'u', 'v', 'w', 'x', 'y'}:
        from nas_vm_dns import POLICY

        assert value['guest_dns_policy'] == POLICY
    if value.get('diagnostic_reference_only'):
        assert attempt in {'p', 'y'} and engine == 'jenkins' and phase == 'rust-jenkins'
        assert value['failed_original_leroy_reference']['diagnostic_reference_only'] is True


def approval_for(folder, engine, *, current):
    import run_nas_day_window as day

    matches = [(p, read(p)) for p in folder.parent.glob('day-window-plan-*/approval.json')]
    matches = [(p, v) for p, v in matches if v.get('comparison_rounds') == [folder.name] and v.get('engine') == engine]
    assert len(matches) == 1
    path, value = matches[0]
    validate_scope(value, folder.name, engine)
    assert value['script_sha256'] == {name: vm.digest(vm.ROOT / name) for name in day.SOURCES}
    expected = (binding(value['resource_profile'], upstream_transport=True, guest_dns=True, resident=True, resident_attempt=value['attempt']) if value['attempt'] in {'v', 'w', 'x', 'y'} else
                binding(value['resource_profile'], upstream_transport=True, guest_dns=True) if value['attempt'] in {'t', 'u'} else
                binding(value['resource_profile'], upstream_transport=True) if value['attempt'] in {'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y'} else
                binding(value['resource_profile'], diagnostic_reference=True) if value.get('diagnostic_reference_only') else
                binding(value['resource_profile']))
    assert value['original_workload_binding'] == expected
    if current:
        day.validate_approval(value)
        assert time.time() < value['absolute_deadline_epoch'] - 900
    return path, value


def expected_marker(folder, engine):
    path, approval = approval_for(folder, engine, current=False)
    return {'qualification_source': 'complete_unchanged_original_job', 'source_commit': vm.COMMIT,
            'engine': engine, 'round': folder.name, 'approval_sha256': vm.digest(path),
            'original_workload_binding': approval['original_workload_binding'],
            'synthetic_capacity_qualified': False, 'original_ci_result_required': True,
            'fixture_limits_changed': False, 'original_ci_results_reused': False,
            'diagnostic_reference_only': approval.get('diagnostic_reference_only', False)}


def retain(folder, engine):
    _, approval = approval_for(folder, engine, current=True)
    assert vm.ROUND == folder.name and vm._GUEST_PIN is not None
    assert vm._GUEST_PIN['labels'] == {'io.leroy.nas-release-target': vm.COMMIT,
                                     'io.leroy.comparison': folder.name, 'io.leroy.engine': engine}
    from nas_verified_container import verify_program

    constants = {'WINDOW': approval['window'], 'ROUND': folder.name,
                 'GUARD_SHA': approval['script_sha256']['scripts/nas_resource_window_guard.py'],
                 'DEADLINE': approval['absolute_deadline_epoch']}
    program = verify_program(vm._GUEST_PIN) + '\n' + ''.join(k + '=' + repr(v) + '\n' for k, v in constants.items()) + r'''
import hashlib,json,pathlib,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity')/WINDOW
assert root.resolve()==root and root.stat().st_uid==0 and root.stat().st_mode&0o077==0
guard=root/'guard.py';statefile=root/'state.json'
assert all(p.resolve(strict=True)==p and p.stat().st_uid==0 and p.stat().st_mode&0o077==0 for p in (guard,statefile))
assert hashlib.sha256(guard.read_bytes()).hexdigest()==GUARD_SHA
state=json.loads(statefile.read_text())
assert state['phase']=='paused' and state['owned_vm_process']['pid']==PIN['pid']
assert state['owned_vm_process']['container_id']==PIN['container_id']
assert state['deadline']==DEADLINE and state['comparison_rounds']==[ROUND]
assert time.time()<state['deadline']-900
print(json.dumps({'window_paused':True,'owned_vm_identity_verified':True}))
'''
    assert json.loads(vm.remote(program, sudo=True, timeout=30)) == {
        'window_paused': True, 'owned_vm_identity_verified': True}
    value = expected_marker(folder, engine)
    path = folder / (engine + '-original-workload-qualification.json')
    assert not (folder / (engine + '-file-memory-capacity.json')).exists()
    if path.exists():
        assert read(path) == value
    else:
        with path.open('x') as stream:
            stream.write(json.dumps(value, indent=2) + '\n')
    return value


def verify_retained(folder, engine):
    value = read(folder / (engine + '-original-workload-qualification.json'))
    assert value == expected_marker(folder, engine)
    assert not (folder / (engine + '-file-memory-capacity.json')).exists()
    return value
