"""Run one complete original Leroy release after two successful original soak trials.

This is a Leroy acceptance run, not a claim of successful Jenkins parity.
Known Jenkins failures and all earlier failed acceptance runs remain retained.
"""

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

import compare_frozen_postdeploy_group as group
from analyze_existing_host_nas_graphato import quality_tests
from compare_frozen_release_cpu_eight import leroy
from nas_followup_support import production_jobs
from nas_measurement_guard import qualification_report
from nas_ssh import ROOT


def analyze(folder, commit, checkout):
    constants = {}
    for node in ast.parse((checkout / 'deployments/linux/host/postdeploy.py').read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign):
            for name in node.targets:
                if isinstance(name, ast.Name) and name.id in {'WEB_CASES', 'QUALITY_CHECKS'}:
                    constants[name.id] = ast.literal_eval(node.value)
    required = {'web': {'browser-core', *('browser-' + name for name in constants['WEB_CASES'])},
                'quality': set(constants['QUALITY_CHECKS'])}
    assert len(required['web']) == 21 and len(required['quality']) == 8
    before = group.read(folder / 'leroy-target-before.json')['manifest']
    suites = {}
    for suite in ('web', 'quality'):
        root = folder / ('graphato-postdeploy-' + suite)
        run = group.read(root / 'leroy-run.json')
        item, = (item for item in run['artifacts'] if PurePosixPath(item['name']).name == 'artifacts.tar.gz')
        name = PurePosixPath(item['name'])
        assert not name.is_absolute() and '..' not in name.parts
        assert len(PurePosixPath(item['step_id']).parts) == 1 and item['step_id'] not in {'.', '..'}
        path = (root / 'leroy-artifacts' / item['step_id']).joinpath(*name.parts).resolve()
        assert path.is_relative_to((root / 'leroy-artifacts').resolve())
        # Win32 glob traversal can silently omit a collected archive beyond the
        # legacy path limit. Resolve its verified API metadata instead.
        if os.name == 'nt':
            value = str(path)
            path = Path('\\\\?\\UNC\\' + value[2:] if value.startswith('\\\\') else '\\\\?\\' + value)
        assert path.stat().st_size == item['size']
        with path.open('rb') as stream:
            archive_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        assert archive_sha == item['sha256']
        files = {}
        with tarfile.open(path) as archive:
            for member in archive:
                assert member.isfile() and 0 <= member.size <= 64 * 1024**2
                assert not PurePosixPath(member.name).is_absolute() and '..' not in PurePosixPath(member.name).parts
                assert member.name not in files and len(files) < 1000
                files[member.name] = archive.extractfile(member).read()
        receipt = json.loads(files['result.json'])
        assert receipt['commit'] == commit and receipt['suite'] == suite and receipt['requestedGroup'] == 'all'
        assert set(receipt['checks']) == required[suite]
        assert receipt['cleanupComplete'] and not receipt['reused'] and not receipt['cancelled']
        assert receipt['runtimeImageId'] == before['runtimeImageId']
        assert receipt['sourceSha256'] == before['files']['verification-source.tar.gz']
        assert receipt['buildTimestamp'] == before['build']['timestamp']
        assert not any('leroy-http-metadata' in name for name in files), 'An observer run cannot prove original acceptance'
        assert (run['status'] == 'succeeded') == receipt['passed']
        value = {'receipt': receipt, 'run_id': run['id'], 'archive_sha256': archive_sha}
        if suite == 'quality':
            value['test_details'] = quality_tests(files, {'identity': receipt, 'checks': receipt['checks']})
            rust = group.rust_summary(files['server-test.log'])
            reference = group.read(ROOT / 'test-results/nas-parity/followup/candidates/graphato' / commit /
                                   'controlled-groups/quality-server-test-round-1/leroy-complete-rust-proof.json')['rust']
            assert rust['expected'] == reference['expected']
            assert rust['test_inventory_sha256'] == reference['test_inventory_sha256']
            value['full_rust_inventory'] = rust
        elif not receipt['checks']['browser-soak']['passed']:
            value['soak_failure'] = json.loads(files['browser-soak/open/results.json'])
        suites[suite] = value
    parent = group.read(folder / 'graphato-release-acceptance/leroy-run.json')
    success = all(row['receipt']['passed'] for row in suites.values())
    assert (parent['status'] == 'succeeded') == success
    report = {'at': group.timestamp(), 'commit': commit, 'target_cpus': 8, 'suites': suites,
              **qualification_report(folder, ('leroy',)),
              'parent': {'run_id': parent['id'], 'status': parent['status']},
              'all_29_original_groups_executed_under_leroy': True,
              'all_original_workloads_successful_under_leroy': success,
              'successful_both_engine_comparison_proven': False,
              'application_source_changed': False, 'application_rate_limits_changed': False,
              'original_failed_comparison_replaced': False, 'production_modified': False,
              'production_replacement_ready': False,
              'scope': 'One complete original Leroy release on the isolated eight-CPU application target; Jenkins parity and production configuration remain separate'}
    group.write(folder / 'analysis.json', report)
    print(json.dumps({'original_leroy_release_complete': True, 'all_29_groups_passed': success,
                      'parent': report['parent'], 'production_replacement_ready': False}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--reason', required=True)
    args = parser.parse_args()
    assert re.fullmatch('[a-f0-9]{40}', args.commit)
    base = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / args.commit
    prerequisites = []
    for number in (1, 2):
        path = base / ('controlled-groups/web-soak-cpu-eight-round-' + str(number)) / 'analysis.json'
        proof = group.read(path)
        assert proof['engines']['leroy']['requested_passed'] is True
        assert proof['application_source_changed'] is False and proof['same_baseline_snapshot'] is True
        prerequisites.append({'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                              'leroy_passed': True, 'jenkins_passed': proof['engines']['jenkins']['requested_passed']})
    rust = group.read(base / 'controlled-groups/quality-server-test-round-1/full-rust-pair-inventory-proof.json')
    assert rust['full_inventory_matches_original'] is True
    assert all(row['rust']['expected'] == 1657 and row['rust']['ok'] == 1625
               and row['rust']['failed'] == 0 and row['rust']['ignored'] == 32
               for row in rust['engines'].values())
    frozen = group.read(base / 'frozen-master.json')
    assert frozen['commit'] == args.commit and not frozen['application_patches_applied']
    checkout = (ROOT / frozen['checkout']).resolve()
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip() == args.commit
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=checkout)
    override = ROOT / '.local/nas-parity/vm/target-cpu-eight.json'
    assert group.read(override) == {'services': {'vm': {'cpus': 8, 'environment': {'VM_CPUS': '8'}}}}
    group.COMPOSE.extend(['-f', str(override)])
    scenario = group.read(base / 'scenarios/root-private-existing-host/scenario.json')
    folder = base / 'controlled-groups/full-release-leroy-cpu-eight-round-1'
    folder.mkdir(parents=True, exist_ok=True)
    prepared = {'commit': args.commit, 'target_cpus': 8, 'baseline_snapshot': scenario['baseline_snapshot'],
                'reason': args.reason, 'prerequisites': prerequisites, 'engines': ['leroy']}
    if (folder / 'prepared.json').exists():
        existing = group.read(folder / 'prepared.json')
        assert all(existing[key] == value for key, value in prepared.items()), 'Resume only the identical original run'
    else:
        group.write(folder / 'prepared.json', {'at': group.timestamp(), **prepared,
                    'production_before': production_jobs(), 'all_triggers_disabled': True,
                    'application_patches_applied': False, 'jenkins_failure_not_waived': True})
    leroy(folder, args.commit, scenario['baseline_snapshot'])
    group.write(folder / 'production-after.json', production_jobs())
    analyze(folder, args.commit, checkout)
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=checkout)


if __name__ == '__main__':
    main()
