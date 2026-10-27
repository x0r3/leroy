"""Execute both original full release pipelines against the same NAS Linux baseline.

No Graphato source, test, rate-limit, or fixture-resource changes. Earlier failed
acceptance runs stay retained. Resume uses the existing CI run, never a retry.
"""

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import tarfile
import threading
import time
from pathlib import Path, PurePosixPath

import compare_frozen_postdeploy_group as group
import nas_release_vm as vm
from analyze_existing_host_nas_graphato import quality_tests
from compare_frozen_release_cpu_eight import jenkins, leroy
from nas_followup_support import inner, production_jobs
from nas_gitea_target import idle
from nas_graphato_release_state import VM_PROGRAM
from nas_measurement_guard import begin, finish, qualification_report
from nas_ssh import ROOT

POSTGRES_INIT = False
CHECK_GUEST_DNS = False
SEPARATE_CAPACITY_REFERENCE = False
PAGE_REPORTING_ORDER = 4


def configure_page_reporting(order):
    global PAGE_REPORTING_ORDER
    assert type(order) is int and order in {0, 4}
    PAGE_REPORTING_ORDER = order


def preflight_source_service(folder):
    """Read the existing owned Git dependency before allocating or dispatching CI."""
    info = json.loads(inner('inspect', 'gitea'))[0]
    assert info['Config']['Labels'].get('io.leroy.nas-parity') == 'true'
    assert info['State']['Running'], 'Owned Git service is stopped; restore its existing container before CI'
    health = inner('exec', 'gitea', 'wget', '-q', '-O', '-', 'http://127.0.0.1:3000/api/healthz', timeout=45)
    repository = '/data/git/repositories/gitea-admin/graphato.git'
    assert inner('exec', 'gitea', 'git', '-c', 'safe.directory=' + repository, '-C', repository,
                 'cat-file', '-t', vm.COMMIT).strip() == 'commit'
    value = {'commit': vm.COMMIT, 'container_id': info['Id'], 'image': info['Image'],
             'configuration_sha256': hashlib.sha256(json.dumps(info['Config'], sort_keys=True).encode()).hexdigest(),
             'mounts': info['Mounts'], 'healthy': True,
             'health_response_sha256': hashlib.sha256(health.encode()).hexdigest(),
             'git_objects_or_refs_changed': False, 'production_modified': False}
    marker = folder / 'source-service.json'
    if marker.exists():
        assert all(group.read(marker)[key] == item for key, item in value.items()
                   if key != 'health_response_sha256'), 'Owned source service changed; retain the existing attempt'
    else:
        group.write(marker, value)


def monitor(folder, stopped):
    """Observe load; optionally reclaim only the SSD test guest's clean cache."""
    last_relief = 0
    while not stopped.is_set():
        value = {'at': group.timestamp()}
        try:
            # Boundaries still scan all history. During a running comparison,
            # changed build counters detect overlap without rereading every old
            # XML record under NAS I/O pressure.
            value['production'] = production_jobs(history=False)
        except (RuntimeError, subprocess.TimeoutExpired, ValueError, OSError) as error:
            value['production_observation_error'] = type(error).__name__
        try:
            # An unavailable production read must not disable the owned VM's
            # resource observations. Boundary history still qualifies overlap.
            value['host'] = json.loads(vm.remote(r'''
import json,pathlib
memory={line.split(':')[0]:int(line.split()[1]) for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:','MemAvailable:','SwapTotal:','SwapFree:'))}
swap={line.split()[0]:int(line.split()[1]) for line in pathlib.Path('/proc/vmstat').read_text().splitlines() if line.startswith(('pswpin ','pswpout ','oom_kill '))}
pressure={name:pathlib.Path('/proc/pressure',name).read_text() for name in ('cpu','memory','io')}
print(json.dumps({'memory_kib':memory,'vmstat':swap,'pressure':pressure,'loadavg':pathlib.Path('/proc/loadavg').read_text().strip()}))
''', timeout=30))
            info = vm.state()
            if info and info['State']['Running']:
                value['vm_disk'] = vm.disk_health()
                if vm.RESOURCE_PROFILE in vm.MEMORY_PRESSURE_PROFILES:
                    from nas_vm_memory_pressure import observe_outer_memory_pressure

                    value['owned_vm_memory_pressure'] = observe_outer_memory_pressure(info['Config']['Labels']['io.leroy.engine'])
                if vm.RESOURCE_PROFILE == 'nas-6g-ssd' and time.monotonic() - last_relief >= 90:
                    from nas_vm_cache import host_needs_cache_relief, relieve_cache

                    if host_needs_cache_relief(value['host']['memory_kib']):
                        last_relief = time.monotonic()
                        relief = {'at': group.timestamp(), 'host_before_kib': value['host']['memory_kib'],
                                  **relieve_cache()}
                        with (folder / 'vm-cache-relief.jsonl').open('a', encoding='utf-8') as stream:
                            stream.write(json.dumps(relief) + '\n')
                        value['test_guest_cache_relief'] = relief
                        print(json.dumps({'engine': relief['engine'], 'test_guest_clean_cache_relief':
                                          relief['clean_cache_relief_performed']}), flush=True)
            if value.get('production', {}).get('active_builds'):
                print(json.dumps({'production_overlap_observed': value['production']['active_builds'],
                                  'functional_test_continues': True, 'load_comparison_qualified': False}), flush=True)
        except (RuntimeError, subprocess.TimeoutExpired, ValueError, OSError) as error:
            value['observation_error'] = type(error).__name__
        with (folder / 'live-observations.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(value) + '\n')
        stopped.wait(60)


def target(commit):
    value = json.loads(vm.guest('sudo python3 -B -', 'COMMIT=' + repr(commit) + '\n' + VM_PROGRAM, timeout=180))
    info = vm.state()
    assert info['State']['Running']
    value['outer_vm_resources'] = {key: info['HostConfig'][key] for key in ('Memory', 'MemorySwap', 'NanoCpus')}
    if vm.VM_IO_LIMITS:
        limits = vm.VM_IO_LIMITS
        expected_io = {'BlkioDeviceReadBps': [{'Path': limits['device'], 'Rate': limits['read_bps']}],
                       'BlkioDeviceWriteBps': [{'Path': limits['device'], 'Rate': limits['write_bps']}]}
        if limits.get('target') == 'qemu-disk':
            expected_io = {key: [] for key in expected_io}
            value['guest_disk_io_throttle'] = vm.disk_health()['io_throttle']
            assert value['guest_disk_io_throttle'] == {'read_bps': limits['read_bps'], 'write_bps': limits['write_bps']}
        value['outer_vm_io_limits'] = {key: info['HostConfig'][key] for key in expected_io}
        assert value['outer_vm_io_limits'] == expected_io
    value['outer_vm_state'] = {key: info['State'][key] for key in ('Running', 'OOMKilled', 'ExitCode')}
    value['guest_resources'] = json.loads(vm.guest('python3 -B -',
        "import json,os,pathlib\nprint(json.dumps({'cpu_count':os.cpu_count(),"
        "'memory_total_kib':next(int(line.split()[1]) for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemTotal:'))}))",
        timeout=45))
    if vm.RESOURCE_PROFILE in vm.PAGE_REPORTING_PROFILES:
        value['guest_free_page_reporting'] = json.loads(vm.guest('python3 -B -',
            "import json,pathlib\nprint(json.dumps({'order':int(pathlib.Path('/sys/module/page_reporting/parameters/page_reporting_order').read_text())}))",
            timeout=45))
        assert value['guest_free_page_reporting']['order'] == PAGE_REPORTING_ORDER
    if vm.RESOURCE_PROFILE in vm.MEMORY_PRESSURE_PROFILES:
        from nas_vm_memory_pressure import observe_outer_memory_pressure

        value['outer_vm_memory_pressure'] = observe_outer_memory_pressure(info['Config']['Labels']['io.leroy.engine'])
    value['physical_target'] = 'NAS 192.168.178.97; own-kernel KVM guest'
    if CHECK_GUEST_DNS:
        from nas_vm_dns import observe

        value['test_environment_dns'] = observe()
    if vm.RESOURCE_PROFILE in vm.GUEST_SWAP_PROFILES:
        from nas_vm_guest_swap import observe_guest_swap

        value['guest_swap_configuration'] = observe_guest_swap()
    if vm.RESOURCE_PROFILE in vm.FILE_MEMORY_PROFILES:
        from nas_vm_file_memory import observe_file_memory

        value['file_memory_configuration'] = observe_file_memory()
    value['captured_at'] = group.timestamp()
    if POSTGRES_INIT:
        from nas_vm_postgres_init import PROOF

        proof = json.loads(vm.guest('sudo python3 -B -', PROOF, timeout=45))
        assert proof == {'override_present': True, 'postgres_init': True}
        value['separate_test_environment_postgres_init'] = proof
    return value


def capture_final_target(folder, engine, commit):
    """Retain terminal CI results even when the resource guard stopped its VM."""
    assert engine in {'leroy', 'jenkins'} and commit == vm.COMMIT
    available = folder / (engine + '-target-after.json')
    unavailable = folder / (engine + '-target-after-unavailable.json')
    assert not available.exists() and not unavailable.exists(), 'Retain the first final observation'

    def owned_state():
        info = vm.state()
        assert info['Config']['Labels']['io.leroy.nas-release-target'] == commit
        assert info['Config']['Labels']['io.leroy.comparison'] == vm.ROUND
        assert info['Config']['Labels']['io.leroy.engine'] == engine
        return info

    info = owned_state()
    if info['State']['Running']:
        try:
            value = target(commit)
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            # A concurrent guard shutdown can occur during the guest read.
            # A failed read of a still-running or different VM remains an error.
            info = owned_state()
            if info['State']['Running']:
                raise
        else:
            group.write(available, value)
            return
    group.write(unavailable, {
        'at': group.timestamp(), 'engine': engine, 'commit': commit,
        'comparison_round': vm.ROUND, 'available': False, 'reason': 'owned_target_vm_stopped',
        'outer_vm_state': {key: info['State'][key] for key in ('Running', 'OOMKilled', 'ExitCode')},
        'original_ci_restarted': False, 'original_ci_archive': False,
        'postrun_target_state_verified': False, 'full_release_acceptance_complete': False,
    })


def restore(folder, engine, commit, baseline, *, page_reporting_order=4, early_memory_pressure=False,
            nas_local_capacity=False, original_workload_qualification=False):
    global CHECK_GUEST_DNS
    CHECK_GUEST_DNS = original_workload_qualification and folder.name.startswith(('day-t-', 'day-u-', 'acceptance-20261017-v-', 'acceptance-20261017-w-', 'acceptance-20261017-x-'))
    configure_page_reporting(page_reporting_order)
    assert commit == vm.COMMIT and baseline == vm.SNAPSHOT
    marker = folder / (engine + '-target-before.json')
    if marker.exists():
        assert group.read(marker)['manifest']['commit'] == commit
        return  # Only preparation resumes here; the CI start marker governs dispatch.
    idle()
    preparing = folder / (engine + '-preparation.json')
    if not preparing.exists():
        production_before = begin(folder, engine + '-restore')
        vm.stop()
        group.write(preparing, {'at': group.timestamp(), 'production_guard_before': production_before,
                               'engine': engine, 'commit': commit, 'baseline': baseline})
        vm.start(engine, postgres_init=POSTGRES_INIT,
                 memory_pressure_folder=folder if early_memory_pressure else None)
    else:
        info = vm.state()
        assert info and info['Config']['Labels']['io.leroy.engine'] == engine and info['State']['Running'], \
            'Incomplete preparation requires investigation; no implicit disk replacement'
        assert info['Config']['Labels']['io.leroy.comparison'] == vm.ROUND
        vm.wait_ready()
        vm.guest('sudo python3 - start', (ROOT / 'infra/vm/graphato-lifecycle.py').read_text(), timeout=300)
    if CHECK_GUEST_DNS:
        from nas_vm_dns import apply

        apply(folder, engine)
    if vm.RESOURCE_PROFILE in vm.PAGE_REPORTING_PROFILES:
        from nas_vm_page_reporting import apply_guest_page_reporting

        apply_guest_page_reporting(folder, engine, order=page_reporting_order)
    if vm.RESOURCE_PROFILE in vm.MEMORY_PRESSURE_PROFILES:
        from nas_vm_memory_pressure import apply_outer_memory_pressure

        apply_outer_memory_pressure(folder, engine)
    if vm.RESOURCE_PROFILE in vm.PROACTIVE_CACHE_PROFILES:
        from nas_vm_cache import start_guest_guard

        start_guest_guard(folder, engine)
    before_probes = None
    if vm.RESOURCE_PROFILE == vm.DISK_QOS_FILE_MEMORY_PROFILE:
        before_probes = target(commit)
        group.write(folder / (engine + '-baseline-before-probes.json'), {
            'at': group.timestamp(), 'containers': before_probes['containers'],
            'guest_disk_io_throttle': before_probes['guest_disk_io_throttle'], 'original_ci_dispatched': False})
        assert len(before_probes['containers']) == 4 and all(
            row['running'] and row['health'] == 'healthy' for row in before_probes['containers'])
    if vm.RESOURCE_PROFILE in vm.FILE_MEMORY_PROFILES:
        if original_workload_qualification:
            assert not nas_local_capacity and not SEPARATE_CAPACITY_REFERENCE
            from nas_original_workload import retain

            retain(folder, engine)
        elif SEPARATE_CAPACITY_REFERENCE:
            from nas_vm_capacity_reference import retain

            retain(folder, engine)
        else:
            from nas_vm_file_capacity import qualify

            qualify(folder, engine, local_admission=nas_local_capacity)
    probe = folder / (engine + '-storage-probe.json')
    if not probe.exists():
        group.write(probe, {'at': group.timestamp(), 'guest': vm.storage_probe(), 'qemu': vm.disk_health()})
    health = vm.disk_health()
    assert not health['cache']['no-flush'] and health['cache']['direct'] == (vm.DISK_CACHE == 'none')
    assert all(value == 0 for key, value in health['counters'].items() if key.startswith('failed_'))
    assert not health['flush_error_trace']
    value = target(commit)
    group.write(folder / (engine + '-baseline-health-observation.json'), {
        'at': group.timestamp(), 'containers': value['containers'],
        'health_probes': value['health_probes'], 'original_ci_dispatched': False})
    assert len(value['containers']) == 4 and all(c['running'] and c['health'] == 'healthy' for c in value['containers'])
    if before_probes is not None:
        assert value['containers'] == before_probes['containers'], 'Supplemental probes changed baseline container state or restart counts'
    assert value['postdeploy_control_directory']['uid'] == 0 and value['postdeploy_control_directory']['mode'] == '0o700'
    assert value['outer_vm_resources']['NanoCpus'] == 6 * 10**9 and value['guest_resources']['cpu_count'] == 6
    assert value['outer_vm_resources']['Memory'] == vm.CONTAINER_MEMORY_GIB * 1024**3
    assert all(row['state'] == 'missing' for row in value['receipt']['suites'].values()), 'Baseline contains prior receipts'
    scenario = group.read(ROOT / 'test-results/nas-parity/followup/candidates/graphato' / commit /
                          'scenarios/root-private-existing-host/scenario.json')
    assert value['manifest'] == scenario['baseline_release']
    group.write(marker, value)
    record_boot_memory(folder)
    finish(folder, engine + '-restore', group.read(preparing)['production_guard_before'])
    print(json.dumps({'engine': engine, 'nas_baseline_ready': True, 'prior_receipts': False}), flush=True)


def artifact_path(root, engine, filename, folder):
    if engine == 'leroy':
        items = group.read(root / 'leroy-run.json')['artifacts']
        archive_root = root / 'leroy-artifacts'
        item, = (row for row in items if PurePosixPath(row['name']).name == filename)
        step = PurePosixPath(item['step_id'])
        assert len(step.parts) == 1 and step.name not in {'.', '..'}
        path = archive_root / step.name / item['name']
    else:
        number = group.read(folder / 'jenkins-start.json')['builds'][root.name]
        archive_root = root / ('jenkins-' + str(number) + '-artifacts')
        item, = (row for row in group.read(root / 'jenkins-artifact-index.json')
                 if PurePosixPath(row['name']).name == filename)
        path = archive_root / item['name']
    name = PurePosixPath(item['name'])
    assert not name.is_absolute() and '..' not in name.parts
    path = path.resolve()
    assert path.is_relative_to(archive_root.resolve())
    if os.name == 'nt':
        text = str(path)
        path = Path('\\\\?\\UNC\\' + text[2:] if text.startswith('\\\\') else '\\\\?\\' + text)
    assert path.stat().st_size == item['size']
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    assert digest == item['sha256']
    return path, digest


def browser_inventory(checkout, cases):
    """Read the original case identities without executing or editing tests."""
    root = checkout / 'apps/desktop/e2e-web'
    literal = r"('(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\")"
    pattern = r'\bawait\s+(?:h\.)?check\(\s*' + literal
    core = [ast.literal_eval(match) for match in re.findall(pattern, (root / 'runner.mjs').read_text())]
    assert len(core) == 21 and len(set(core)) == len(core)
    calls = [ast.literal_eval(match) for path in root.glob('*.mjs')
             for match in re.findall(pattern, path.read_text())]
    open_cases = [case for case in cases if case != 'previews']
    assert all(calls.count(case) == 1 for case in open_cases), 'Original open-case inventory changed'
    previews = (root / 'previews-runner.mjs').read_text()
    engines, = re.findall(r'for\s*\(\s*const engine of \[([a-z,]+)\]', previews)
    suffix, = re.findall(r'results.push\(\{name:`\$\{engine.name\(\)\}([^`]+)`,passed:true\}\)', previews)
    assert engines.split(',') == ['firefox', 'chromium'] and 'previews' in cases
    return {'browser-core': {'field': 'name', 'identities': core, 'worker_suite': 'core'},
            'browser-previews': {'field': 'name', 'identities': [engine + suffix for engine in engines.split(',')],
                                 'worker_suite': 'previews'},
            **{'browser-' + case: {'field': 'id', 'identities': [case], 'worker_suite': 'open'} for case in open_cases}}


def browser_result_proof(files, checks, inventory):
    """Count the canonical results once and expose aborted case inventories."""
    values = {}
    for name, expected in sorted(inventory.items()):
        path = name + '/results.json'
        rows = json.loads(files[path]) if path in files else []
        assert isinstance(rows, list)
        assert all(isinstance(row, dict) and type(row.get('passed')) is bool for row in rows)
        assert all(row.get('suite') == expected['worker_suite'] for row in rows)
        nested = name + '/' + expected['worker_suite'] + '/results.json'
        if nested in files:
            original = json.loads(files[nested])
            assert rows == [{**row, 'suite': expected['worker_suite']} for row in original], \
                'Aggregate and original worker results disagree'
        observed = [row[expected['field']] for row in rows if expected['field'] in row]
        assert all(not row['passed'] for row in rows if expected['field'] not in row)
        assert len(observed) == len(set(observed)) and all(item in expected['identities'] for item in observed)
        complete = observed == expected['identities'] and len(observed) == len(rows)
        assert complete or not checks[name]['passed'], 'Successful group has incomplete original case proof'
        assert all(row['passed'] for row in rows) or not checks[name]['passed']
        outcome = ('passed' if checks[name]['passed'] else 'failed_before_original_cases' if not rows else
                   'failed_with_incomplete_case_inventory' if not complete else
                   'failed_during_original_cases' if not all(row['passed'] for row in rows) else
                   'failed_after_original_cases')
        values[name] = {'original_result_count': len(rows), 'original_results': rows,
                        'expected_original_case_count': len(expected['identities']),
                        'missing_original_cases': [item for item in expected['identities'] if item not in observed],
                        'complete_original_case_inventory_proven': complete, 'outcome_phase': outcome}
    return values


def component_inventory(log):
    text = re.sub(r'\x1b\[[0-9;]*m', '', log.decode(errors='replace'))
    ends = list(re.finditer(r'^(?:ℹ|#) duration_ms [\d.]+\s*$', text, re.MULTILINE))
    if not ends:
        return {'available': False}
    start = ends[-2].end() if len(ends) > 1 else 0
    block = text[start:ends[-1].start()]
    names = re.findall(r'^[✔✖] (.+?) \([\d.]+ms\)$', block, re.MULTILINE)
    counts = {key: int(value) for key, value in re.findall(
        r'^(?:ℹ|#) (tests|pass|fail|cancelled|skipped|todo) (\d+)$', block, re.MULTILINE)}
    if 'tests' not in counts:
        return {'available': False}
    return {'available': True, 'counts': counts, 'test_names_recorded': len(names),
            'test_inventory_sha256': hashlib.sha256(json.dumps(sorted(names)).encode()).hexdigest(),
            'failed_tests': re.findall(r'^✖ (.+?) \([\d.]+ms\)$', block, re.MULTILINE),
            'complete_terminal_inventory': len(names) == len(set(names)) == counts['tests'] and
                sum(counts.get(key, 0) for key in ('pass', 'fail', 'cancelled', 'skipped', 'todo')) == counts['tests']}


def quality_inventory_proof(files, receipt, reference):
    """Certify the original inventory even when a completed test suite fails."""
    details = quality_tests(files, {'identity': receipt, 'checks': receipt['checks']})
    rust = group.rust_summary(files['server-test.log'])
    rust_complete = all(rust[key] == reference['rust'][key]
                        for key in ('expected', 'test_inventory_sha256'))
    python = details['deployment_python']
    counts = [row['tests'] for row in python.get('summaries', [python])]
    python_complete = counts == reference['python_suite_test_counts']
    components = component_inventory(files['frontend-and-deployment.log'])
    component_complete = components.get('complete_terminal_inventory', False) and all(
        components[key] == reference['components'][key] for key in ('test_names_recorded', 'test_inventory_sha256'))
    if receipt['checks']['server-test']['passed']:
        assert rust_complete, 'Successful Rust check is missing original test identities'
    if receipt['checks']['frontend-and-deployment']['passed']:
        assert python_complete, 'Successful frontend check is missing original Python suites'
        assert component_complete, 'Successful frontend check is missing original component identities'
    return {'test_details': details, 'full_rust_inventory': rust,
            'same_full_rust_inventory_as_original': rust_complete,
            'same_python_suite_counts_as_original': python_complete,
            'complete_rust_and_python_inventory_proven': rust_complete and python_complete,
            'components': components, 'same_full_component_inventory_as_original': component_complete,
            'complete_original_quality_test_inventories_proven': rust_complete and python_complete and component_complete}


def original_quality_reference():
    root = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / vm.COMMIT
    rust = group.read(root / 'controlled-groups/quality-server-test-round-1/leroy-complete-rust-proof.json')['rust']
    assert rust['expected'] == 1657
    path, = (root / 'scenarios/root-private-existing-host/graphato-postdeploy-quality/jenkins-8-artifacts').rglob('artifacts.tar.gz')
    with tarfile.open(path) as archive:
        receipt = json.loads(archive.extractfile('result.json').read())
        log = archive.extractfile('frontend-and-deployment.log').read().decode(errors='replace')
    assert receipt['commit'] == vm.COMMIT and receipt['checks']['frontend-and-deployment']['passed']
    counts = [int(value) for value in re.findall(r'^Ran (\d+) tests? in ', log, re.MULTILINE)]
    assert counts == [146, 17, 13, 7, 4, 8]
    components = component_inventory(log.encode())
    assert components['complete_terminal_inventory'] and components['test_names_recorded'] == 98
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'rust': rust, 'python_suite_test_counts': counts,
            'components': components,
            'python_reference_archive_sha256': sha,
            'python_reference_archive': path.relative_to(ROOT).as_posix()}


def same_guest_resources(first, second, boot_memory=None):
    """Accept small observed kernel reservations only with equal physical boot maps."""
    assert set(first) == set(second) == {'cpu_count', 'memory_total_kib'}
    if first['cpu_count'] != second['cpu_count']:
        return False
    difference = abs(first['memory_total_kib'] - second['memory_total_kib'])
    if difference <= 4:
        return True
    if difference > 32 or not boot_memory or set(boot_memory) != {'jenkins', 'leroy'}:
        return False
    first_boot, second_boot = boot_memory['jenkins'], boot_memory['leroy']
    if not first_boot.get('bios_e820') or first_boot['bios_e820'] != second_boot.get('bios_e820'):
        return False
    totals = [re.findall(r'Memory: \d+K/(\d+)K available', '\n'.join(row['kernel_memory_lines']))
              for row in (first_boot, second_boot)]
    return len(totals[0]) == 1 and totals[0] == totals[1]


def memory_boot_proof(folder):
    path = folder / 'guest-boot-memory-proof.json'
    return group.read(path)['boot_memory'] if path.exists() else None


def record_boot_memory(folder):
    program = 'ROOT=' + repr(vm.DISK_ROOT + '/runs/' + vm.ROUND) + '\n' + r'''
import json,pathlib,re
result={}
for engine in ('jenkins','leroy'):
 path=pathlib.Path(ROOT)/engine/'serial.log'
 if not path.is_file():continue
 assert not path.is_symlink() and path.stat().st_size<8*1024**2
 text=path.read_text(errors='replace')
 ranges=re.findall(r'BIOS-e820: \[mem 0x[0-9a-f]+-0x[0-9a-f]+\] (?:usable|reserved|ACPI data|ACPI NVS)',text)
 result[engine]={'bios_e820':ranges[:30],'kernel_memory_lines':re.findall(r'Memory: [^\r\n]+',text)[:3]}
print(json.dumps(result))
'''
    data = json.loads(vm.remote(program, sudo=True, timeout=30))
    path = folder / 'guest-boot-memory-proof.json'
    if path.exists():
        previous = group.read(path)['boot_memory']
        assert all(data[key] == value for key, value in previous.items())
    group.write(path, {'at': group.timestamp(), 'commit': vm.COMMIT, 'boot_memory': data,
                      'application_source_changed': False, 'application_tests_changed': False})


def verify_guest_swap_environment(folder):
    if vm.RESOURCE_PROFILE not in vm.GUEST_SWAP_PROFILES:
        return
    configurations = []
    for engine in ('jenkins', 'leroy'):
        before = group.read(folder / (engine + '-target-before.json'))['guest_swap_configuration']
        assert before['path'] == '/var/lib/leroy-vm/guest-swap/swapfile'
        assert before['file_bytes'] == 4 * 1024**3 and before['priority'] == 10
        assert 4 * 1024**2 - 16 <= before['kernel_swap_kib'] <= 4 * 1024**2
        after = folder / (engine + '-target-after.json')
        if after.exists():
            assert group.read(after)['guest_swap_configuration'] == before
        configurations.append(before)
    assert configurations[0] == configurations[1], 'Both engines require the same candidate guest swap configuration'


def analyze(folder, checkout):
    verify_guest_swap_environment(folder)
    if vm.RESOURCE_PROFILE in vm.FILE_MEMORY_PROFILES:
        from nas_vm_file_memory import verify_paired_environment

        verify_paired_environment(folder)
        if SEPARATE_CAPACITY_REFERENCE:
            from nas_vm_capacity_reference import binding

            for engine in ('leroy', 'jenkins'):
                proof = group.read(folder / (engine + '-file-memory-capacity.json'))
                assert proof['separate_capacity_reference'] == binding()
    constants = {}
    for node in ast.parse((checkout / 'deployments/linux/host/postdeploy.py').read_text()).body:
        if isinstance(node, ast.Assign):
            for name in node.targets:
                if isinstance(name, ast.Name) and name.id in {'WEB_CASES', 'QUALITY_CHECKS'}:
                    constants[name.id] = ast.literal_eval(node.value)
    required = {'web': {'browser-core', *('browser-' + name for name in constants['WEB_CASES'])},
                'quality': set(constants['QUALITY_CHECKS'])}
    assert len(required['web']) == 21 and len(required['quality']) == 8
    inventory = browser_inventory(checkout, constants['WEB_CASES'])
    assert set(inventory) == required['web']
    suites, parents, targets = {}, {}, {}
    quality_reference = original_quality_reference()
    missing = []
    for engine in ('jenkins', 'leroy'):
        for pipeline, filename in [('graphato-postdeploy-web', 'artifacts.tar.gz'),
                                   ('graphato-postdeploy-quality', 'artifacts.tar.gz'),
                                   ('graphato-release-acceptance', 'release-status.json')]:
            root = folder / pipeline
            items = (group.read(root / 'leroy-run.json')['artifacts'] if (root / 'leroy-run.json').exists()
                     else []) if engine == 'leroy' else group.read(root / 'jenkins-artifact-index.json')
            if not any(PurePosixPath(row['name']).name == filename for row in items):
                missing.append({'engine': engine, 'pipeline': pipeline, 'artifact': filename})
    if missing or any(not (folder / (engine + '-target-after.json')).exists()
                      for engine in ('jenkins', 'leroy')):
        analyze_incomplete(folder, required, inventory, quality_reference, missing)
        return
    for engine in ('jenkins', 'leroy'):
        before = group.read(folder / (engine + '-target-before.json'))
        after = group.read(folder / (engine + '-target-after.json'))
        assert before['manifest'] == after['manifest']
        targets[engine] = {'before': before, 'after': after}
        parent_root = folder / 'graphato-release-acceptance'
        parent = group.read(parent_root / ('leroy-run.json' if engine == 'leroy' else 'jenkins-build.json'))
        parents[engine] = parent['status'] if engine == 'leroy' else parent['result']
        for suite in ('web', 'quality'):
            path, sha = artifact_path(folder / ('graphato-postdeploy-' + suite), engine, 'artifacts.tar.gz', folder)
            files = {}
            expanded = 0
            with tarfile.open(path) as archive:
                for member in archive:
                    name = PurePosixPath(member.name)
                    assert member.isfile() and 0 <= member.size <= 64 * 1024**2
                    assert not name.is_absolute() and '..' not in name.parts
                    assert member.name not in files and len(files) < 1000
                    expanded += member.size
                    assert expanded <= 256 * 1024**2
                    files[member.name] = archive.extractfile(member).read()
            receipt = json.loads(files['result.json'])
            assert receipt['commit'] == vm.COMMIT and receipt['suite'] == suite and receipt['requestedGroup'] == 'all'
            assert set(receipt['checks']) == required[suite]
            assert receipt['cleanupComplete'] and not receipt['reused'] and not receipt['cancelled']
            assert receipt['runtimeImageId'] == before['manifest']['runtimeImageId']
            assert receipt['sourceSha256'] == before['manifest']['files']['verification-source.tar.gz']
            assert receipt['buildTimestamp'] == before['manifest']['build']['timestamp']
            assert not any('leroy-http-metadata' in name for name in files)
            value = {'receipt': receipt, 'archive_sha256': sha,
                     'failed_groups': [name for name, check in receipt['checks'].items() if not check['passed']]}
            if suite == 'web':
                case_results = browser_result_proof(files, receipt['checks'], inventory)
                value['browser_case_results'] = case_results
                value['all_original_browser_groups_executed'] = all(row['original_result_count'] for row in case_results.values())
                value['all_original_browser_cases_executed'] = all(
                    row['complete_original_case_inventory_proven'] for row in case_results.values())
            if suite == 'quality':
                try:
                    value.update(quality_inventory_proof(files, receipt, quality_reference))
                except (AssertionError, KeyError, ValueError) as error:
                    if receipt['checks']['server-test']['passed'] and receipt['checks']['frontend-and-deployment']['passed']:
                        raise
                    value['incomplete_test_detail_proof'] = {'error_type': type(error).__name__,
                        'complete_rust_and_python_inventory_proven': False}
                    value['complete_rust_and_python_inventory_proven'] = False
                    value['complete_original_quality_test_inventories_proven'] = False
                value['quality_workload_completion_unproved_groups'] = [
                    name for name, check in receipt['checks'].items()
                    if name not in {'frontend-and-deployment', 'server-test'} and not check['passed']]
                value['all_original_quality_workloads_executed'] = (
                    value['complete_original_quality_test_inventories_proven'] and
                    not value['quality_workload_completion_unproved_groups'])
            elif not receipt['checks']['browser-soak']['passed'] and 'browser-soak/open/results.json' in files:
                value['soak_failure'] = json.loads(files['browser-soak/open/results.json'])
            suites.setdefault(suite, {})[engine] = value
        success = all(row[engine]['receipt']['passed'] for row in suites.values())
        assert (parents[engine] == ('succeeded' if engine == 'leroy' else 'SUCCESS')) == success
        path, sha = artifact_path(parent_root, engine, 'release-status.json', folder)
        receipt = json.loads(path.read_text())
        assert {k: v for k, v in receipt.items() if k != 'observedAt'} == {
            k: v for k, v in after['receipt'].items() if k != 'observedAt'}
        assert receipt['commit'] == vm.COMMIT and receipt['activeRelease']
        assert (receipt['status'] == 'verified') == success
        targets[engine]['parent_receipt_sha256'] = sha
    assert targets['jenkins']['before']['manifest'] == targets['leroy']['before']['manifest']
    for resource in ('outer_vm_resources', 'guest_resources'):
        expected = targets['jenkins']['before'][resource]
        assert all((same_guest_resources(targets[engine][phase][resource], expected, memory_boot_proof(folder)) if resource == 'guest_resources'
                    else targets[engine][phase][resource] == expected)
                   for engine in ('jenkins', 'leroy') for phase in ('before', 'after'))
    if vm.RESOURCE_PROFILE in vm.MEMORY_PRESSURE_PROFILES:
        expected_high = group.read(folder / 'prepared.json')['owned_vm_memory_pressure']['memory_high_bytes']
        assert all(targets[engine][phase]['outer_vm_memory_pressure']['memory_high_bytes'] == expected_high
                   for engine in ('jenkins', 'leroy') for phase in ('before', 'after'))
    comparison = {}
    for suite, names in required.items():
        comparison[suite] = {name: {'jenkins_passed': suites[suite]['jenkins']['receipt']['checks'][name]['passed'],
                                   'leroy_passed': suites[suite]['leroy']['receipt']['checks'][name]['passed']}
                             for name in sorted(names)}
        for name, row in comparison[suite].items():
            row['same_group_status'] = row['jenkins_passed'] == row['leroy_passed']
            if suite == 'web':
                row['outcome_phases'] = {engine: suites[suite][engine]['browser_case_results'][name]['outcome_phase']
                                         for engine in ('jenkins', 'leroy')}
    report = {'at': group.timestamp(), 'commit': vm.COMMIT, 'baseline': group.read(folder / 'prepared.json')['baseline'],
              'target_cpus': 6, 'target_guest_memory_mb': vm.GUEST_MEMORY_MB, 'disk_cache': vm.DISK_CACHE,
              'physical_target': 'NAS',
              'suites': suites, 'parents': parents, 'targets': targets, 'original_group_comparison': comparison,
              'original_quality_inventory_reference': quality_reference,
              'same_original_group_statuses_both': all(row['same_group_status']
                                                      for names in comparison.values() for row in names.values()),
              **qualification_report(folder, ('jenkins', 'leroy', 'jenkins-restore', 'leroy-restore')),
              'all_29_original_group_receipts_present_both': True,
              'all_29_original_groups_executed_both': all(
                  suites['web'][engine]['all_original_browser_cases_executed'] and
                  suites['quality'][engine]['all_original_quality_workloads_executed']
                  for engine in ('jenkins', 'leroy')),
              'expected_original_browser_cases_per_engine': sum(len(row['identities']) for row in inventory.values()),
              'all_original_workloads_successful_both': all(v['receipt']['passed'] for engines in suites.values() for v in engines.values()),
              'application_source_changed': False, 'application_tests_changed': False,
              'application_rate_limits_changed': False, 'fixture_resource_limits_changed': False,
              'same_original_runtime_image_both': True, 'same_snapshot_both': True,
              'same_vm_resource_configuration_both': True,
              **({'same_owned_vm_memory_high_both': True} if vm.RESOURCE_PROFILE in vm.MEMORY_PRESSURE_PROFILES else {}),
              'original_failed_comparisons_replaced': False, 'production_modified': False,
              'production_replacement_ready': False,
              'scope': 'Original full release gate on a NAS own-kernel target with pre-existing root-private control directory; retained fresh-installation failure remains separate'}
    group.write(folder / 'analysis.json', report)
    print(json.dumps({'full_release_comparison_complete': True, 'parents': parents,
                      'all_original_workloads_successful_both': report['all_original_workloads_successful_both']}), flush=True)


def analyze_incomplete(folder, required, inventory, quality_reference, missing):
    """Keep failed original CI evidence distinct from supplementary target reads."""
    suites, parents, targets = {}, {}, {}
    for engine in ('jenkins', 'leroy'):
        before = group.read(folder / (engine + '-target-before.json'))
        after_path = folder / (engine + '-target-after.json')
        after = group.read(after_path) if after_path.exists() else None
        unavailable = None
        if after is not None:
            assert before['manifest'] == after['manifest']
            assert same_guest_resources(before['guest_resources'], after['guest_resources'], memory_boot_proof(folder))
            assert before['outer_vm_resources'] == after['outer_vm_resources']
        else:
            unavailable = group.read(folder / (engine + '-target-after-unavailable.json'))
            assert unavailable['available'] is False and unavailable['commit'] == vm.COMMIT
            assert unavailable['engine'] == engine and not unavailable['outer_vm_state']['Running']
        targets[engine] = {'before': before, 'after': after, 'after_unavailable': unavailable}
        parent = group.read(folder / 'graphato-release-acceptance' /
                            ('leroy-run.json' if engine == 'leroy' else 'jenkins-build.json'))
        parents[engine] = parent['status'] if engine == 'leroy' else parent['result']
        assert parents[engine] in {'failed', 'succeeded', 'interrupted', 'timed_out', 'cancelled', 'FAILURE', 'SUCCESS'}
        for suite in ('web', 'quality'):
            root = folder / ('graphato-postdeploy-' + suite)
            child_started = (root / 'leroy-run.json').exists() if engine == 'leroy' else True
            items = (group.read(root / 'leroy-run.json')['artifacts'] if child_started
                     else []) if engine == 'leroy' else group.read(root / 'jenkins-artifact-index.json')
            available = any(PurePosixPath(row['name']).name == 'artifacts.tar.gz' for row in items)
            value = {'original_ci_run_started': child_started,
                     'original_ci_archive_available': available, 'checks': {},
                     'complete_original_inventory_proven': False}
            if available:
                path, sha = artifact_path(root, engine, 'artifacts.tar.gz', folder)
                with tarfile.open(path) as archive:
                    files, expanded = {}, 0
                    for member in archive:
                        name = PurePosixPath(member.name)
                        assert member.isfile() and not name.is_absolute() and '..' not in name.parts
                        assert member.name not in files and 0 <= member.size <= 64 * 1024**2
                        expanded += member.size
                        assert len(files) < 1000 and expanded <= 256 * 1024**2
                        files[member.name] = archive.extractfile(member).read()
                receipt = json.loads(files['result.json'])
                assert receipt['commit'] == vm.COMMIT and receipt['suite'] == suite
                assert receipt['runtimeImageId'] == before['manifest']['runtimeImageId']
                assert receipt['sourceSha256'] == before['manifest']['files']['verification-source.tar.gz']
                assert set(receipt['checks']) <= required[suite]
                value.update(receipt=receipt, checks=receipt['checks'], archive_sha256=sha)
                if suite == 'web':
                    proof = browser_result_proof(files, receipt['checks'], inventory)
                    value['browser_case_results'] = proof
                    value['complete_original_inventory_proven'] = all(
                        row['complete_original_case_inventory_proven'] for row in proof.values())
                else:
                    try:
                        value.update(quality_inventory_proof(files, receipt, quality_reference))
                        value['complete_original_inventory_proven'] = value[
                            'complete_original_quality_test_inventories_proven']
                    except (AssertionError, KeyError, ValueError) as error:
                        value['incomplete_test_detail_proof'] = type(error).__name__
            diagnostic = folder / (engine + '-quality-interruption-proof.json')
            web_diagnostic = folder / (engine + '-web-interruption-proof.json')
            if suite == 'web' and web_diagnostic.exists():
                supplemental = group.read(web_diagnostic)
                receipt = supplemental['receipt']
                assert receipt['commit'] == vm.COMMIT and receipt['suite'] == 'web'
                assert receipt['runtimeImageId'] == before['manifest']['runtimeImageId']
                assert receipt['sourceSha256'] == before['manifest']['files']['verification-source.tar.gz']
                archive_path = folder / (engine + '-web-incomplete-target-diagnostics.tar.gz')
                with archive_path.open('rb') as stream:
                    assert hashlib.file_digest(stream, 'sha256').hexdigest() == supplemental['archive_sha256']
                with tarfile.open(archive_path) as archive:
                    assert json.loads(archive.extractfile('result.json').read()) == receipt
                value['supplementary_target_diagnostic'] = web_diagnostic.name
                value['supplementary_checks'] = receipt['checks']
                value['supplementary_receipt_completed'] = receipt['completedAt'] is not None
                value['supplementary_cleanup_complete'] = receipt['cleanupComplete']
                value['supplementary_original_browser_inventory_certified'] = False
                value['supplementary_diagnostic_is_original_ci_archive'] = False
            if suite == 'quality' and diagnostic.exists():
                supplemental = group.read(diagnostic)
                assert supplemental['receipt']['commit'] == vm.COMMIT
                value['supplementary_target_diagnostic'] = diagnostic.name
                value['supplementary_checks'] = supplemental['receipt']['checks']
                value['supplementary_receipt_completed'] = supplemental['receipt']['completedAt'] is not None
                value['supplementary_guest_oom_kill'] = supplemental['guest_oom_kill']
                archive_path = folder / (engine + '-quality-incomplete-target-diagnostics.tar.gz')
                with archive_path.open('rb') as stream:
                    assert hashlib.file_digest(stream, 'sha256').hexdigest() == supplemental['archive_sha256']
                with tarfile.open(archive_path) as archive:
                    frontend = archive.extractfile('frontend-and-deployment.log').read()
                    rust_log = archive.extractfile('server-test.log').read().decode(errors='replace')
                components = component_inventory(frontend)
                python_counts = [int(count) for count in re.findall(
                    r'^Ran (\d+) tests? in ', frontend.decode(errors='replace'), re.MULTILINE)]
                value['supplementary_test_inventory'] = {
                    'python_suite_counts': python_counts,
                    'same_python_suite_counts_as_original': python_counts == quality_reference['python_suite_test_counts'],
                    'components': components,
                    'rust_terminal_test_events': len(re.findall(
                        r'"type":\s*"test"[^\n]*"event":\s*"(?:ok|failed|ignored)"', rust_log)),
                    'is_original_ci_archive': False}
            value['missing_original_group_receipts'] = sorted(required[suite] - value['checks'].keys())
            suites.setdefault(suite, {})[engine] = value
    assert targets['jenkins']['before']['manifest'] == targets['leroy']['before']['manifest']
    assert targets['jenkins']['before']['outer_vm_resources'] == targets['leroy']['before']['outer_vm_resources']
    assert same_guest_resources(targets['jenkins']['before']['guest_resources'],
                                targets['leroy']['before']['guest_resources'], memory_boot_proof(folder))
    matrix = {suite: {name: {engine: suites[suite][engine]['checks'].get(name, {}).get('passed')
                             for engine in ('jenkins', 'leroy')} for name in sorted(names)}
              for suite, names in required.items()}
    report = {'at': group.timestamp(), 'commit': vm.COMMIT, 'parents': parents, 'suites': suites,
              'targets': targets, 'original_group_comparison': matrix, 'missing_original_ci_artifacts': missing,
              'original_quality_inventory_reference': quality_reference,
              **qualification_report(folder, ('jenkins', 'leroy', 'jenkins-restore', 'leroy-restore')),
              'original_ci_parent_runs_finished_both': True,
              'all_29_original_group_receipts_present_both': False,
              'all_29_original_groups_executed_both': False,
              'original_target_after_available_both': all(row['after'] is not None for row in targets.values()),
              'all_original_workloads_successful_both': False,
              'same_original_runtime_image_both': True, 'same_snapshot_both': True,
              'application_source_changed': False, 'application_tests_changed': False,
              'application_rate_limits_changed': False, 'fixture_resource_limits_changed': False,
              'supplementary_diagnostics_are_original_ci_artifacts': False,
              'production_modified': False, 'production_replacement_ready': False}
    group.write(folder / 'analysis.json', report)
    print(json.dumps({'original_ci_parent_runs_finished_both': True, 'parents': parents,
                      'full_release_acceptance_complete': False, 'missing_original_ci_artifacts': missing}), flush=True)


def main():
    global POSTGRES_INIT, SEPARATE_CAPACITY_REFERENCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', required=True)
    parser.add_argument('--engine', choices=['jenkins', 'leroy', 'both'], default='both')
    parser.add_argument('--resource-profile', choices=sorted({'nas-4g5', 'nas-6g-io-limited', *vm.SSD_PROFILES}), default='nas-4g5')
    parser.add_argument('--first-engine', choices=['jenkins', 'leroy'], default='jenkins')
    parser.add_argument('--postgres-init', action='store_true', help='Qualified test baseline override; fresh namespace only')
    parser.add_argument('--page-reporting-order', choices=(0, 4), type=int, default=4)
    parser.add_argument('--early-memory-pressure', action='store_true')
    parser.add_argument('--nas-local-capacity', action='store_true')
    parser.add_argument('--original-workload-qualification', action='store_true')
    parser.add_argument('--memory-trace', action='store_true')
    parser.add_argument('--separate-capacity-reference', action='store_true')
    parser.add_argument('--matching-ci-background', action='store_true',
                        help='Require live production-matching CI slots and retain private Jenkins during both engines')
    args = parser.parse_args()
    if args.original_workload_qualification:
        assert args.matching_ci_background and not args.nas_local_capacity and not args.separate_capacity_reference
    configure_page_reporting(args.page_reporting_order)
    POSTGRES_INIT = args.postgres_init
    SEPARATE_CAPACITY_REFERENCE = args.separate_capacity_reference
    folder = (ROOT / args.folder).resolve()
    assert folder.is_relative_to(ROOT / 'test-results/nas-parity/followup')
    vm.configure(folder.name, args.resource_profile)
    folder.mkdir(parents=True, exist_ok=True)
    assert not (folder / 'final-state.json').exists(), 'Completed attempts stay retained; use a new comparison namespace'
    frozen = group.read(ROOT / 'test-results/nas-parity/followup/candidates/graphato' / vm.COMMIT / 'frozen-master.json')
    checkout = (ROOT / frozen['checkout']).resolve()
    assert frozen['commit'] == vm.COMMIT and not frozen['application_patches_applied']
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip() == vm.COMMIT
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=checkout)
    preflight_source_service(folder)
    prepared = {'commit': vm.COMMIT, 'baseline': group.read(vm.LOCAL / 'staged.json'), 'target_cpus': 6,
                'target_guest_memory_mb': vm.GUEST_MEMORY_MB, 'disk_cache': vm.DISK_CACHE,
                'minimum_host_swap_free_mb': vm.MIN_HOST_SWAP_MB,
                'minimum_host_available_memory_mb': vm.MIN_HOST_AVAILABLE_MB,
                'comparison_namespace': vm.ROUND, 'engines': ['jenkins', 'leroy'], 'application_patches_applied': False,
                'all_triggers_disabled': True, 'reason': 'User requested full original release acceptance on NAS under both CI engines'}
    if POSTGRES_INIT:
        from nas_vm_postgres_init import PROGRAM

        qualification = group.read(ROOT / 'test-results/nas-parity/followup/offline-forensics-20261014/postgres-init-probe.json')
        assert qualification['controlled_orphan_reproduction_passed']
        assert not folder.name.startswith(('full-release-controller512-20261013', 'full-release-nas-202610'))
        prepared['separate_test_environment_postgres_init'] = {
            'enabled_both_engines': True, 'staging_program_sha256': hashlib.sha256(PROGRAM.encode()).hexdigest(),
            'lifecycle_program_sha256': hashlib.sha256((ROOT / 'infra/vm/graphato-lifecycle.py').read_bytes()).hexdigest(),
            'original_source_and_tests_modified': False, 'original_failed_attempts_replaced': False}
    if SEPARATE_CAPACITY_REFERENCE:
        from nas_vm_capacity_reference import binding

        prepared['separate_capacity_reference'] = binding()
    engines = [args.first_engine, 'leroy' if args.first_engine == 'jenkins' else 'jenkins']
    if args.resource_profile != 'nas-4g5' or args.first_engine != 'jenkins':
        prepared.update(resource_profile=args.resource_profile, engines=engines, vm_io_limits=vm.VM_IO_LIMITS)
    if args.resource_profile in vm.SSD_PROFILES:
        prepared.update(ssd_storage_proof=group.read(vm.LOCAL / 'staged-ssd.json'),
                        minimum_test_disk_free_mb=vm.MIN_DISK_FREE_MB,
                        test_guest_cache_policy={'trigger_host_swap_free_mb': vm.MIN_HOST_SWAP_MB + 2048,
                           'minimum_guest_available_mb': 1024, 'minimum_guest_cached_mb': 768,
                           'minimum_seconds_between_relief': 90, 'drop_caches_value': 1,
                           'host_kernel_modified': False, 'fixture_resource_limits_changed': False})
        if args.resource_profile in vm.PROACTIVE_CACHE_PROFILES:
            from nas_vm_cache import guard_program

            prepared['test_guest_cache_policy'] = {'execution': 'Verified own KVM guest process',
                'interval_seconds': 30, 'minimum_guest_available_mb': 1024, 'minimum_guest_cached_mb': 768,
                'program_sha256': hashlib.sha256(guard_program().encode()).hexdigest(),
                'drop_caches_value': 1, 'host_kernel_modified': False, 'fixture_resource_limits_changed': False}
        if args.resource_profile in vm.PAGE_REPORTING_PROFILES:
            prepared['guest_free_page_reporting'] = {'order': args.page_reporting_order,
                'minimum_reported_block_bytes': 4096 * (1 << args.page_reporting_order),
                'guest_capacity_changed': False, 'host_kernel_modified': False, 'fixture_resource_limits_changed': False}
        if args.resource_profile in vm.MEMORY_PRESSURE_PROFILES:
            from nas_vm_memory_pressure import high_bytes_for_profile

            prepared['owned_vm_memory_pressure'] = {'memory_high_bytes': high_bytes_for_profile(args.resource_profile),
                'hard_limits_changed': False, 'global_host_kernel_settings_changed': False,
                'fixture_resource_limits_changed': False}
    if args.early_memory_pressure:
        prepared['early_memory_pressure'] = True
    if args.nas_local_capacity:
        prepared['nas_local_capacity'] = True
    if args.original_workload_qualification:
        prepared['original_workload_qualification'] = True
        prepared['synthetic_capacity_qualified'] = False
    if args.memory_trace:
        prepared['nas_local_memory_trace'] = True
    if args.matching_ci_background:
        from nas_ci_background import capacity_proof

        prepared['matching_ci_background'] = True
        prepared['ci_slots'] = 2
        prepared['ci_capacity_alignment_proof_sha256'] = capacity_proof()
    marker = folder / 'prepared.json'
    if marker.exists():
        assert all(group.read(marker)[key] == value for key, value in prepared.items())
    else:
        group.write(marker, {'at': group.timestamp(), **prepared, 'production_before': production_jobs()})
    group.restore, group.target, group.capture_final_target = restore, target, capture_final_target
    if args.memory_trace or args.page_reporting_order != 4 or args.early_memory_pressure or args.nas_local_capacity or args.original_workload_qualification:
        def measured_restore(folder, engine, commit, baseline):
            restore(folder, engine, commit, baseline, page_reporting_order=args.page_reporting_order,
                    early_memory_pressure=args.early_memory_pressure, nas_local_capacity=args.nas_local_capacity,
                    original_workload_qualification=args.original_workload_qualification)
            if args.memory_trace and not (folder / (engine + '-memory-trace.json')).exists():
                from nas_vm_memory_trace import start_trace

                start_trace(folder, engine)

        group.restore = measured_restore
    stopped = threading.Event()
    observer = threading.Thread(target=monitor, args=(folder, stopped), daemon=True)
    observer.start()
    try:
        for engine in engines:
            if args.engine in {engine, 'both'}:
                execute = jenkins if engine == 'jenkins' else leroy
                if args.matching_ci_background:
                    from nas_ci_background import prepare, record

                    prepare(folder, engine)
                    execute(folder, vm.COMMIT, vm.SNAPSHOT, keep_private_jenkins=True)
                    record(folder, engine, 'after')
                else:
                    execute(folder, vm.COMMIT, vm.SNAPSHOT)
                if args.memory_trace:
                    from diagnose_nas_release_group import collect_memory_evidence

                    collect_memory_evidence(folder, engine)
                if vm.RESOURCE_PROFILE in vm.PROACTIVE_CACHE_PROFILES:
                    from nas_vm_cache import collect_guest_guard

                    if not (folder / (engine + '-guest-cache-observations.json')).exists():
                        collect_guest_guard(folder, engine)
    finally:
        stopped.set()
        observer.join(timeout=60)
    if all(any((folder / (engine + suffix)).exists() for suffix in
               ('-target-after.json', '-target-after-unavailable.json')) for engine in ('jenkins', 'leroy')):
        if args.matching_ci_background:
            from nas_ci_background import paired_proof

            group.write(folder / 'ci-background-comparison.json', paired_proof(folder))
        analyze(folder, checkout)
        idle()
        vm.stop()
        group.write(folder / 'final-state.json', {'at': group.timestamp(), 'vm_running': vm.state()['State']['Running'],
                    'production_after': production_jobs(), 'windows_vm_started': False, 'engine_overlays_retained': True})
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=checkout)


if __name__ == '__main__':
    try:
        main()
    except subprocess.TimeoutExpired:
        raise SystemExit('SSH observation timed out; retain and resume the existing CI run without redispatch') from None
