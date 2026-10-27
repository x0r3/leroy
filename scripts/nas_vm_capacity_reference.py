"""Separate supplemental capacity evidence from fresh, original CI execution.

The supplemental stress in E passed memory integrity but interrupted Graphato's
database lease. Never reuse that application state or call it a CI success.
"""

import json

import nas_release_vm as vm

REFERENCE = 'day-e-rust-leroy-20261015'
PHYSICAL_SOURCES = ('scripts/nas_release_vm.py', 'infra/vm/launch.py',
                    'scripts/nas_vm_memory_pressure.py', 'scripts/nas_vm_file_memory.py',
                    'scripts/nas_vm_file_capacity.py', 'scripts/nas_vm_guest_swap.py',
                    'scripts/nas_vm_page_reporting.py', 'infra/vm/graphato-lifecycle.py')


def read(path):
    return json.loads(path.read_text())


def binding(profile=None):
    profile = vm.RESOURCE_PROFILE if profile is None else profile
    base = vm.ROOT / 'test-results/nas-parity/followup'
    case = base / REFERENCE
    window = base / 'resource-window-day-20261015-e-rust-leroy'
    plan = read(base / 'day-window-plan-20261015-e-rust-leroy/approval.json')
    assert profile == vm.PROTECTED_FILE_MEMORY_PROFILE
    assert plan['source_commit'] == vm.COMMIT and plan['resource_profile'] == profile
    sources = {name: vm.digest(vm.ROOT / name) for name in PHYSICAL_SOURCES}
    assert all(plan['script_sha256'][name] == sha for name, sha in sources.items()), 'Capacity environment code changed'
    prepared = read(case / 'prepared.json')
    assert prepared['commit'] == vm.COMMIT and prepared['resource_profile'] == profile
    result = read(window / 'window-result.json')
    assert all(result[key] is True for key in ('all_seven_original_services_restored_healthy',
               'native_jenkins_quiet', 'infrastructure_unchanged', 'controller_process_unchanged', 'controller_no_new_oom'))
    assert read(window / 'closed-disk-archive.json')['source_removed'] is True
    assert not read(window / 'restored-window.json').get('host_reserve_stop')
    assert read(case / 'no-original-ci-dispatch.json')['original_ci_dispatched'] is False
    summary = read(case / 'leroy-memory-summary.json')
    assert summary['aligned_guest_host_samples'] > 0
    assert summary['minimum_host_available_kib'] >= vm.MIN_HOST_AVAILABLE_MB * 1024
    assert summary['minimum_host_swap_free_kib'] >= vm.MIN_HOST_SWAP_MB * 1024
    capacity = read(case / 'leroy-file-memory-capacity.json')
    assert capacity['qualified_synthetic_capacity'] and capacity['all_page_markers_intact']
    assert capacity['allocated_mib'] == 5888 and capacity['hold_seconds'] >= 60
    assert capacity['original_fixture_limits_emulated'] is True
    full = next(row for row in capacity['phases'] if row['kind'] == 'allocated' and row['allocated_mib'] == 5888)
    held = [row for row in capacity['phases'] if row['kind'] == 'held']
    assert len(held) >= 3 and all(row['allocated_mib'] == 5888 for row in held)
    assert held[-1]['at_epoch'] - full['at_epoch'] >= 60
    limits = capacity['limits']
    assert limits['memory_bytes'] == limits['memory_and_swap_bytes'] == 6 * 1024**3
    assert limits['nano_cpus'] == 2 * 10**9 and limits['cgroup_swap_max'] == 0
    assert capacity['phases'][-1]['kind'] == 'stopped' and capacity['phases'][-1]['all_page_markers_intact']
    assert limits['image'] == 'sha256:6251c60f499e41e706613f931bf281ce52312b957d5a6a123cf4e27dd3242585'
    assert capacity['original_ci_dispatched'] is False and capacity['application_source_or_tests_changed'] is False
    files = {name: vm.digest(case / name) for name in ('leroy-file-memory-capacity.json',
             'leroy-memory-summary.json', 'prepared.json', 'no-original-ci-dispatch.json')}
    return {'reference_case': REFERENCE, 'reference_files_sha256': files, 'physical_sources_sha256': sources,
            'resource_profile': profile, 'original_ci_results_reused': False,
            'capacity_test_executed_in_current_guest': False, 'fresh_application_baseline_required': True,
            'reference_application_health_failed': True}


def retain(folder, engine):
    reference = binding()
    proof = read(vm.ROOT / 'test-results/nas-parity/followup' / REFERENCE / 'leroy-file-memory-capacity.json')
    proof['separate_capacity_reference'] = reference
    path = folder / (engine + '-file-memory-capacity.json')
    if path.exists():
        assert read(path) == proof, 'Retain the first reference binding'
    else:
        path.write_text(json.dumps(proof, indent=2) + '\n')
    return reference
