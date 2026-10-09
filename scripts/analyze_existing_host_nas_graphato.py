"""Compare original complete suites and exact failure signatures without declaring failed jobs successful."""

import ast
import hashlib
import json
import re
import tarfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import PurePosixPath

from analyze_current_nas_graphato import suite_receipt
from nas_candidate_paths import candidate_checkout
from nas_ssh import ROOT
from stage_nas_production_graphato import COMMIT


def read(path):
    return json.loads(path.read_text())


def bundle(folder, engine, pair, receipt):
    root = folder / ('leroy-artifacts' if engine == 'leroy' else f"jenkins-{pair['jenkins']['number']}-artifacts")
    (path,) = root.rglob('artifacts.tar.gz')
    files, total = {}, 0
    with tarfile.open(path) as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            assert member.isfile() and not name.is_absolute() and '..' not in name.parts
            assert member.name not in files and member.size <= 64 * 1024**2
            total += member.size
            assert len(files) < 1000 and total <= 256 * 1024**2
            files[member.name] = archive.extractfile(member).read()
    archived = json.loads(files['result.json'])
    assert all(archived[key] == value for key, value in receipt['identity'].items())
    assert archived['commit'] == COMMIT and archived['checks'].keys() == receipt['checks'].keys()
    assert {name: {'passed': value['passed'], 'exitCode': value['exitCode']} for name, value in archived['checks'].items()} == receipt['checks']
    return files, {'path': path.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                   'members': len(files), 'expanded_bytes': total}


def quality_tests(files, receipt):
    """Compare the original test events, without requiring names introduced by later patches."""
    timings = json.loads(files['rust-test-times.json'])
    assert all(timings[key] == receipt['identity'][key] for key in
               ('commit', 'runtimeImageId', 'sourceSha256', 'buildTimestamp', 'suite'))
    events = []
    for line in files['server-test.log'].decode('utf-8', errors='replace').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    expected = sum(event['test_count'] for event in events
                   if event.get('type') == 'suite' and event.get('event') == 'started')
    terminal = Counter((event['name'], event['event']) for event in events
                       if event.get('type') == 'test' and event.get('event') in {'ok', 'ignored', 'failed'})
    counts = {state: sum(count for (_, event), count in terminal.items() if event == state)
              for state in ('ok', 'ignored', 'failed')}
    assert expected > 0 and sum(counts.values()) == expected
    assert timings['complete'] and timings['expectedTests'] == timings['measuredTests'] == counts['ok'] + counts['failed']
    if receipt['checks']['server-test']['passed']:
        assert counts['failed'] == 0
    normalized = sorted((name, event, count) for (name, event), count in terminal.items())
    python_log = files['frontend-and-deployment.log'].decode('utf-8', errors='replace')
    summaries = re.findall(r'^Ran (\d+) tests? in [\d.]+s\s+\n(OK(?: \([^\n]+\))?|FAILED \([^\n]+\))$',
                           python_log, re.MULTILINE)
    assert summaries, 'The original Python test summaries must be available'
    assert len(summaries) == len(re.findall(r'^Ran \d+ tests? in ', python_log, re.MULTILINE)), (
        'A truncated Python test summary cannot certify complete results')
    python = {'tests': sum(int(count) for count, _ in summaries),
              'result': 'OK' if all(result.startswith('OK') for _, result in summaries)
              else '; '.join(result for _, result in summaries if not result.startswith('OK'))}
    if len(summaries) > 1:
        python['summaries'] = [{'tests': int(count), 'result': result} for count, result in summaries]
    rust = {'expected': expected, **counts,
            'normalized_results_sha256': hashlib.sha256(json.dumps(normalized).encode()).hexdigest()}
    if counts['failed']:
        rust['failed_tests'] = sorted(name for name, event in terminal if event == 'failed')
    return {'rust': rust,
            'deployment_python': python}


def signatures(suite, files, receipt):
    values = {}
    for name in receipt['failed_groups']:
        if suite == 'web' and name == 'browser-merge':
            rows = json.loads(files['browser-merge/open/results.json'])
            row, = [item for item in rows if item['id'] == 'merge']
            assert row['passed'] is False
            values[name] = {'signature': row['error'], 'business_cause_classified': False}
        elif suite == 'web' and name == 'browser-soak':
            rows = json.loads(files['browser-soak/open/results.json'])
            row, = [item for item in rows if item['id'] == 'soak']
            assert row['passed'] is False
            diagnosis = (ROOT / 'test-results/nas-parity/followup/candidates/graphato' / COMMIT
                         / 'scenarios/root-private-existing-host/browser-soak-failure-analysis.json')
            proof = read(diagnosis) if diagnosis.exists() else {}
            classified = proof.get('commit') == COMMIT and proof.get('cause_classified', False)
            classified = classified and row['error'] == proof.get('error')
            if classified:
                checkout = candidate_checkout(COMMIT)
                assert all(hashlib.sha256((checkout / path).read_bytes()).hexdigest() == digest
                           for path, digest in proof['source_sha256'].items())
            values[name] = {'signature': row['error'], 'cause_classified': classified,
                            'underlying_environment_or_timing_cause_proven': False}
            if classified:
                values[name]['cause_evidence'] = diagnosis.relative_to(ROOT).as_posix()
        elif suite == 'quality' and name == 'frontend-and-deployment':
            log = files['frontend-and-deployment.log'].decode('utf-8', errors='replace')
            signature = 'Preview admission requires its dedicated, pre-created runtime mount'
            if 'ERROR: test_current_production_compose_passes_release_policy' in log and 'ValueError: ' + signature in log:
                values[name] = {'signature': signature, 'cause_classified': True,
                                'cause_evidence': 'test-results/nas-parity/followup/production-source-review/failed-groups/failure-signatures.json'}
            else:
                values[name] = {'signature': None, 'cause_classified': False}
        else:
            values[name] = {'signature': None, 'cause_classified': False}
    return values


def main():
    base = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / COMMIT / 'scenarios/root-private-existing-host'
    execution = read(base / 'executions.json')
    activity_path = base / 'production-activity-audit.json'
    if not execution['production_jobs_unchanged'] and not activity_path.exists():
        from audit_nas_production_activity import main as collect_activity

        collect_activity()
    activity = read(activity_path) if activity_path.exists() else None
    assert execution['production_jobs_unchanged'] or (
        activity and activity['read_only'] and activity['all_changed_builds_have_recognized_trigger_causes']
        and not activity['production_modified_by_agent']
        and not activity['production_builds_triggered_by_this_task']
        and set(activity['counter_changes']) == {
            name for name, before in read(base / 'production-jobs-before.json')['jobs'].items()
            if before != read(base / 'production-jobs-after.json')['jobs'][name]}
        and all(row['before'] == read(base / 'production-jobs-before.json')['jobs'][name]
                and row['after'] == read(base / 'production-jobs-after.json')['jobs'][name]
                for name, row in activity['counter_changes'].items()))
    assert execution['same_baseline_snapshot'] and execution['no_preexisting_suite_receipts_both']
    assert not execution['application_patches_applied'] and not execution['production_modified']
    scenario = read(base / 'scenario.json')
    targets = {engine: read(base / (engine + '-target-after.json')) for engine in ('jenkins', 'leroy')}
    before = {engine: read(base / (engine + '-target-before.json')) for engine in targets}
    for engine in targets:
        assert targets[engine]['manifest'] == before[engine]['manifest'] == scenario['baseline_release']
        assert all(row['running'] and row['health'] == 'healthy' for row in targets[engine]['containers'])
        assert len(targets[engine]['containers']) == 4
        assert all(row['state'] == 'missing' for row in before[engine]['receipt']['suites'].values())
    source = (candidate_checkout(COMMIT) / 'deployments/linux/host/postdeploy.py').read_text(encoding='utf-8')
    assert hashlib.sha256(source.encode()).hexdigest() == scenario['baseline_release']['files']['deployments/linux/host/postdeploy.py']
    constants = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            for name in node.targets:
                if isinstance(name, ast.Name) and name.id in {'WEB_CASES', 'QUALITY_CHECKS'}:
                    constants[name.id] = ast.literal_eval(node.value)
    required = {'web': {'browser-core', *('browser-' + name for name in constants['WEB_CASES'])},
                'quality': set(constants['QUALITY_CHECKS'])}
    suites, pipelines = {}, {}
    for suite in ('web', 'quality'):
        name = 'graphato-postdeploy-' + suite
        folder = base / name
        pair, run = read(folder / 'pair.json'), read(folder / 'leroy-run.json')
        assert pair['commit'] == run['commit'] == COMMIT and COMMIT in pair['jenkins']['checkout_revisions']
        assert not pair['application_patches_applied'] and not pair['jenkins']['building']
        receipts = {engine: suite_receipt(folder, engine, pair, suite, targets[engine]) for engine in targets}
        archives, errors, test_details = {}, {}, {}
        complete = all(value['receipt_available'] and set(value['checks']) == required[suite]
                       and value['cleanup_complete'] and not value['cancelled'] for value in receipts.values())
        for engine, receipt in receipts.items():
            if receipt['receipt_available']:
                files, archives[engine] = bundle(folder, engine, pair, receipt)
                errors[engine] = signatures(suite, files, receipt)
                if suite == 'quality':
                    test_details[engine] = quality_tests(files, receipt)
        same_checks = complete and receipts['jenkins']['checks'] == receipts['leroy']['checks']
        if suite == 'quality':
            same_checks = same_checks and test_details.get('jenkins') == test_details.get('leroy')
        matched_errors = same_checks and errors.get('jenkins') == errors.get('leroy') and all(
            value['signature'] is not None for value in errors.get('jenkins', {}).values())
        success = same_checks and all(value['complete_suite_passed'] for value in receipts.values())
        classified = matched_errors and all(value.get('cause_classified', False)
                                           for value in errors.get('jenkins', {}).values())
        state = ('validated_current_source_scenario' if success else
                 'matching_application_failure' if classified else
                 'matching_failed_checks' if matched_errors else 'execution_difference')
        suites[suite] = {'required_checks': sorted(required[suite]), 'engines': receipts, 'archives': archives,
                         'all_required_groups_executed': complete, 'same_check_outcomes': same_checks,
                         'failure_signatures': errors, 'same_original_failure_signatures': matched_errors,
                         'test_details': test_details, 'all_failure_causes_classified': classified,
                         'complete_suite_success_both': success}
        pipelines[name] = {'jenkins_build': pair['jenkins']['number'], 'jenkins_result': pair['jenkins']['result'],
                           'leroy_run': run['id'], 'leroy_status': run['status'], 'source_matches': True,
                           'state': state, 'workload_success_both': success,
                           'note': 'Separate full-suite scenario with the same original source and active build, restored from the same root-private host snapshot. Failed assertions remain failures.'}
    folder = base / 'graphato-release-acceptance'
    pair, run = read(folder / 'pair.json'), read(folder / 'leroy-run.json')
    assert pair['commit'] == run['commit'] == COMMIT and COMMIT in pair['jenkins']['checkout_revisions']
    assert run['parent_id'] is None and len(run['children']) == 2
    assert {row['id'] for row in run['children']} == {row['leroy_run'] for row in pipelines.values()}
    assert all(read(base / name / 'leroy-run.json')['parent_id'] == run['id'] for name in pipelines)
    success = all(row['workload_success_both'] for row in pipelines.values())
    matching = all(row['state'] != 'execution_difference' for row in pipelines.values())
    if matching:
        assert (pair['jenkins']['result'] == 'SUCCESS') == success
        assert (run['status'] == 'succeeded') == success
    pipelines['graphato-release-acceptance'] = {'jenkins_build': pair['jenkins']['number'],
             'jenkins_result': pair['jenkins']['result'], 'leroy_run': run['id'], 'leroy_status': run['status'],
             'source_matches': run['commit'] == COMMIT and COMMIT in pair['jenkins']['checkout_revisions'],
             'state': 'validated_current_source_scenario' if success else 'matching_downstream_failure' if matching else 'execution_difference',
             'workload_success_both': success}
    record = {'at': datetime.now(timezone.utc).isoformat(), 'commit': COMMIT, 'scenario': scenario['scenario'],
              'pipelines': pipelines, 'suites': suites, 'same_active_build_both': True,
              'same_prepared_host_snapshot_both': True, 'application_patches_applied': False,
              'all_required_groups_executed_both': all(value['all_required_groups_executed'] for value in suites.values()),
              'no_migration_execution_difference_observed': matching,
              'workload_success_both': success, 'production_modified': False, 'production_replacement_ready': False}
    record['production_job_counters_unchanged'] = execution['production_jobs_unchanged']
    record['independent_production_activity'] = activity
    record['performance_comparison'] = False
    observations_path = base / 'control-plane-observations.jsonl'
    if observations_path.exists():
        assert observations_path.stat().st_size < 8 * 1024**2
        observations = [json.loads(line) for line in observations_path.read_text().splitlines()]
        assert observations and all(set(row['services']) == {'controller', 'postgres', 'runner'}
                                    and row['read_only'] for row in observations)
        service_rows = [service for row in observations for service in row['services'].values()]
        record['sampled_control_plane'] = {
            'evidence': observations_path.relative_to(ROOT).as_posix(),
            'samples': len(observations), 'first_at': observations[0]['at'], 'last_at': observations[-1]['at'],
            'swap_zero_at_all_samples': all(row['swap_current_bytes'] == row['swap_max_bytes'] == 0
                                           for row in service_rows),
            'no_oom_or_restart_observed': all(not row['oom_killed'] and row['restart_count'] == 0
                and int(row['memory_events']['oom']) == int(row['memory_events']['oom_kill']) == 0
                for row in service_rows),
            'every_instant_observed': False, 'previous_interruption_cause_proven': False,
        }
    (base / 'analysis.json').write_text(json.dumps(record, indent=2) + '\n')
    execution['receipt_and_failure_analysis_pending'] = False
    execution['analysis_evidence'] = (base / 'analysis.json').relative_to(ROOT).as_posix()
    (base / 'executions.json').write_text(json.dumps(execution, indent=2) + '\n')
    print(json.dumps({'all_required_groups_executed_both': record['all_required_groups_executed_both'],
                      'no_migration_execution_difference_observed': matching, 'workload_success_both': success}), flush=True)


if __name__ == '__main__':
    main()
