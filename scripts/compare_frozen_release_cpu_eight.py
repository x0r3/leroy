"""Run all original release checks on an eight-CPU isolated target; retain earlier failures."""

import argparse
import ast
import hashlib
import json
import re
import time
from contextlib import ExitStack, closing

import compare_frozen_postdeploy_group as group
import httpx
from analyze_existing_host_nas_graphato import quality_tests
from compare_nas_antares import client
from nas_followup_support import inner, jenkins_api, production_jobs, start_jenkins
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish, qualification_report
from nas_ssh import ROOT
from nas_test_environment import require_current_jenkins

JOBS = {'graphato-release-acceptance', 'graphato-postdeploy-web', 'graphato-postdeploy-quality'}


def collect_final_target(folder, engine, commit):
    """A stopped NAS target has explicit missing evidence, never a fabricated receipt."""
    collector = getattr(group, 'capture_final_target', None)
    if collector is not None:
        return collector(folder, engine, commit)
    group.write(folder / (engine + '-target-after.json'), group.target(commit))


def observe_leroy_runs(folder, run_id, commit):
    """Reuse authenticated reads; transient transport errors never redispatch CI."""
    deadline = time.monotonic() + 9 * 3600
    previous, api = None, None
    with ExitStack() as connections:
        while time.monotonic() < deadline:
            try:
                if api is None:
                    api = connections.enter_context(closing(client()))
                response = api.get('/api/runs/' + run_id)
                response.raise_for_status()
                parent = response.json()
                runs = [parent]
                for child in parent['children']:
                    response = api.get('/api/runs/' + child['id'])
                    response.raise_for_status()
                    runs.append(response.json())
            except (httpx.TransportError, httpx.HTTPStatusError) as error:
                error_name = type(error).__name__
                if isinstance(error, httpx.HTTPStatusError):
                    if error.response.status_code != 401:
                        raise
                    # A saved session can expire during a long original build.
                    # Renew authentication on the next read, never the CI job.
                    connections.close()
                    api = None
                    error_name = 'HTTP401'
                observation = {'at': group.timestamp(), 'engine': 'leroy',
                               'original_parent': run_id, 'observation_error': error_name,
                               'original_ci_restarted': False}
                with (folder / 'leroy-observation-errors.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(observation) + '\n')
                print(json.dumps(observation), flush=True)
                time.sleep(20)
                continue
            assert parent['commit'] == commit and parent['parent_id'] is None
            assert all(row['commit'] == commit and row['pipeline_id'] in JOBS for row in runs)
            assert all(row['parent_id'] == run_id for row in runs[1:])
            state = {row['pipeline_id']: {'id': row['id'], 'status': row['status']} for row in runs}
            group.write(folder / 'leroy-progress.json', {'at': group.timestamp(), 'runs': state})
            if state != previous:
                print(json.dumps({'engine': 'leroy', 'runs': state}), flush=True)
                previous = state
            if all(row['status'] not in group.ACTIVE for row in runs):
                return runs, state
            time.sleep(20)
    raise TimeoutError('Retain active original release; no cancellation or implicit retry')


def leroy(folder, commit, baseline, *, keep_private_jenkins=False):
    marker = folder / 'leroy-start.json'
    if any((folder / ('leroy-target-after' + suffix)).exists() for suffix in ('.json', '-unavailable.json')):
        finish(folder, 'leroy', group.read(marker).get('production_guard_before'))
        return
    if not marker.exists():
        group.write(folder / 'comparison-environment.json', require_current_jenkins())
        group.restore(folder, 'leroy', commit, baseline)
        production_before = begin(folder, 'leroy')
        assert inner('inspect', 'jenkins-parity', '--format', '{{.State.Running}}').strip() == str(keep_private_jenkins).lower()
        with closing(client()) as api:
            assert not any(row['enabled'] for row in api.get('/api/pipelines').json())
            response = api.post('/api/pipelines/graphato-release-acceptance/runs',
                                json={'commit': commit, 'parameters': {'RELEASE_COMMIT': commit}})
            response.raise_for_status()
            started = {'at': group.timestamp(), 'id': response.json()['id'], 'production_guard_before': production_before}
        group.write(marker, started)
        print(json.dumps({'engine': 'leroy', 'release_started': started}), flush=True)
    run_id = group.read(marker)['id']
    runs, state = observe_leroy_runs(folder, run_id, commit)
    parent = runs[0]
    assert set(state) <= JOBS
    if set(state) != JOBS:
        assert parent['status'] in {'interrupted', 'failed', 'timed_out', 'cancelled'}, \
            'Successful release has an incomplete run tree'
        group.write(folder / 'leroy-incomplete-release-tree.json', {
            'at': group.timestamp(), 'parent': run_id, 'parent_status': parent['status'],
            'missing_original_pipelines': sorted(JOBS - set(state)),
            'full_release_acceptance_complete': False, 'original_runs_restarted': False})
    for run in runs:
        destination = folder / run['pipeline_id']
        destination.mkdir(exist_ok=True)
        group.write(destination / 'leroy-run.json', run)
        with closing(client()) as api:
            group.collect_artifacts(api, run, destination)
            for step in run['steps']:
                response = api.get('/api/runs/' + run['id'] + '/logs/' + step['id'])
                response.raise_for_status()
                (destination / ('leroy-' + step['id'] + '.log')).write_text(response.json()['text'], encoding='utf-8')
    collect_final_target(folder, 'leroy', commit)
    finish(folder, 'leroy', group.read(marker).get('production_guard_before'))


def jenkins(folder, commit, baseline, *, keep_private_jenkins=False):
    marker = folder / 'jenkins-start.json'
    if any((folder / ('jenkins-target-after' + suffix)).exists() for suffix in ('.json', '-unavailable.json')):
        finish(folder, 'jenkins', group.read(marker).get('production_guard_before'))
        return
    if not marker.exists():
        group.write(folder / 'comparison-environment.json', require_current_jenkins())
        group.restore(folder, 'jenkins', commit, baseline)
        production_before = begin(folder, 'jenkins')
        if keep_private_jenkins:
            assert require_current_jenkins()['running'], 'Start the matching CI background before restoring the target'
        else:
            start_jenkins()
        state = json.loads(jenkins_api('/api/json?tree=jobs[name,nextBuildNumber,lastBuild[building]]')['text'])
        assert not any((row.get('lastBuild') or {}).get('building') for row in state['jobs'])
        assert not json.loads(jenkins_api('/queue/api/json?tree=items[id]')['text'])['items']
        numbers = {row['name']: row['nextBuildNumber'] for row in state['jobs'] if row['name'] in JOBS}
        assert set(numbers) == JOBS
        jenkins_api('/job/graphato-release-acceptance/buildWithParameters',
                    'RELEASE_COMMIT=' + commit, 'application/x-www-form-urlencoded')
        group.write(marker, {'at': group.timestamp(), 'builds': numbers, 'production_guard_before': production_before})
    builds = group.read(marker)['builds']
    deadline = time.monotonic() + 9 * 3600
    previous = None
    while time.monotonic() < deadline:
        state = {job: group.observe_original_jenkins(folder, job, number) for job, number in builds.items()}
        if any(row is None for row in state.values()):
            time.sleep(20)
            continue
        group.write(folder / 'jenkins-progress.json', {'at': group.timestamp(), 'builds': state})
        if state != previous:
            print(json.dumps({'engine': 'jenkins', 'builds': state}), flush=True)
            previous = state
        if all(row.get('started') and not row.get('building') for row in state.values()):
            break
        parent = state['graphato-release-acceptance']
        if parent.get('started') and not parent.get('building') and not any(
                row.get('building') for row in state.values()):
            queue = json.loads(jenkins_api('/queue/api/json?tree=items[id]')['text'])['items']
            if not queue:
                group.write(folder / 'jenkins-incomplete-release-tree.json', {
                    'at': group.timestamp(), 'original_parent_number': builds['graphato-release-acceptance'],
                    'original_parent_status': parent['result'],
                    'missing_original_pipelines': sorted(job for job, row in state.items() if not row.get('started')),
                    'full_release_acceptance_complete': False, 'original_ci_restarted': False})
                finish(folder, 'jenkins', group.read(marker).get('production_guard_before'))
                raise RuntimeError('Original Jenkins parent finished before all child jobs started; retain this failed attempt')
        time.sleep(20)
    else:
        raise TimeoutError('Retain active Jenkins release; no cancellation or implicit retry')
    for job, number in builds.items():
        destination = folder / job
        destination.mkdir(exist_ok=True)
        group.write(destination / 'jenkins-terminal-observed.json', {'at': group.timestamp(), 'job': job, **state[job]})
        group.collect_original_jenkins(destination, job, number, commit, deadline)
    idle()
    if not keep_private_jenkins:
        inner('stop', '--time', '120', 'jenkins-parity', timeout=150)
    collect_final_target(folder, 'jenkins', commit)
    finish(folder, 'jenkins', group.read(marker).get('production_guard_before'))


def analyze(folder, commit, checkout):
    import tarfile

    constants = {}
    for node in ast.parse((checkout / 'deployments/linux/host/postdeploy.py').read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign):
            for name in node.targets:
                if isinstance(name, ast.Name) and name.id in {'WEB_CASES', 'QUALITY_CHECKS'}:
                    constants[name.id] = ast.literal_eval(node.value)
    required = {'web': {'browser-core', *('browser-' + name for name in constants['WEB_CASES'])},
                'quality': set(constants['QUALITY_CHECKS'])}
    suites = {}
    for suite in ('web', 'quality'):
        values = {}
        for engine in ('leroy', 'jenkins'):
            root = folder / ('graphato-postdeploy-' + suite)
            archive_root = root / ('leroy-artifacts' if engine == 'leroy' else
                                  'jenkins-' + str(group.read(folder / 'jenkins-start.json')['builds'][root.name]) + '-artifacts')
            path, = archive_root.rglob('artifacts.tar.gz')
            files = {}
            with tarfile.open(path) as archive:
                for member in archive:
                    assert member.isfile() and 0 <= member.size <= 64 * 1024**2
                    assert not group.PurePosixPath(member.name).is_absolute() and '..' not in group.PurePosixPath(member.name).parts
                    assert member.name not in files and len(files) < 1000
                    files[member.name] = archive.extractfile(member).read()
            receipt = json.loads(files['result.json'])
            assert receipt['commit'] == commit and receipt['suite'] == suite and receipt['requestedGroup'] == 'all'
            assert set(receipt['checks']) == required[suite]
            assert receipt['cleanupComplete'] and not receipt['reused'] and not receipt['cancelled']
            values[engine] = {'receipt': receipt, 'archive_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            if suite == 'quality':
                values[engine]['test_details'] = quality_tests(files, {'identity': receipt, 'checks': receipt['checks']})
                rust = group.rust_summary(files['server-test.log'])
                reference = group.read(ROOT / 'test-results/nas-parity/followup/candidates/graphato' / commit /
                                       'controlled-groups/quality-server-test-round-1/leroy-complete-rust-proof.json')['rust']
                assert rust['expected'] == reference['expected']
                assert rust['test_inventory_sha256'] == reference['test_inventory_sha256']
                values[engine]['full_rust_inventory'] = rust
            if 'browser-soak' in receipt['checks'] and not receipt['checks']['browser-soak']['passed']:
                values[engine]['soak_failure'] = json.loads(files['browser-soak/open/results.json'])
        for key in ('runtimeImageId', 'sourceSha256', 'buildTimestamp'):
            assert values['jenkins']['receipt'][key] == values['leroy']['receipt'][key]
        suites[suite] = values
    all_success = all(value['receipt']['passed'] for engines in suites.values() for value in engines.values())
    parents = {'leroy': group.read(folder / 'graphato-release-acceptance/leroy-run.json')['status'],
               'jenkins': group.read(folder / 'graphato-release-acceptance/jenkins-build.json')['result']}
    assert (parents['leroy'] == 'succeeded') == all(v['leroy']['receipt']['passed'] for v in suites.values())
    assert (parents['jenkins'] == 'SUCCESS') == all(v['jenkins']['receipt']['passed'] for v in suites.values())
    report = {'at': group.timestamp(), 'commit': commit, 'target_cpus': 8, 'suites': suites, 'parents': parents,
              **qualification_report(folder, ('leroy', 'jenkins')),
              'all_29_original_groups_executed_both': True, 'all_original_workloads_successful_both': all_success,
              'application_source_changed': False, 'application_rate_limits_changed': False,
              'same_original_runtime_image_both': True, 'same_snapshot_both': True,
              'original_failed_comparison_replaced': False, 'production_modified': False,
              'production_replacement_ready': False,
              'scope': 'Original-image full release on an eight-CPU isolated application target; production configuration remains separate'}
    group.write(folder / 'analysis.json', report)
    print(json.dumps({'full_release_comparison_complete': True, 'all_original_workloads_successful_both': all_success,
                      'parents': parents}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    assert re.fullmatch('[a-f0-9]{40}', args.commit)
    base = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / args.commit
    assert (base / 'controlled-groups/web-soak-cpu-eight-round-1/analysis.json').is_file(), 'Complete the CPU-only group experiment first'
    proof = group.read(base / 'controlled-groups/web-soak-cpu-eight-round-1/analysis.json')
    assert all(row['requested_passed'] for row in proof['engines'].values()), 'Do not repeat a known failing full release'
    override = ROOT / '.local/nas-parity/vm/target-cpu-eight.json'
    assert group.read(override) == {'services': {'vm': {'cpus': 8, 'environment': {'VM_CPUS': '8'}}}}
    group.COMPOSE.extend(['-f', str(override)])
    scenario = group.read(base / 'scenarios/root-private-existing-host/scenario.json')
    frozen = group.read(base / 'frozen-master.json')
    assert not frozen['application_patches_applied'] and frozen['commit'] == args.commit
    checkout = (ROOT / frozen['checkout']).resolve()
    folder = base / 'controlled-groups/full-release-cpu-eight-round-1'
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / 'prepared.json').exists():
        group.write(folder / 'prepared.json', {'at': group.timestamp(), 'commit': args.commit,
                    'baseline_snapshot': scenario['baseline_snapshot'], 'production_before': production_jobs(),
                    'application_patches_applied': False, 'all_triggers_disabled': True, 'target_cpus': 8})
    leroy(folder, args.commit, scenario['baseline_snapshot'])
    jenkins(folder, args.commit, scenario['baseline_snapshot'])
    group.write(folder / 'production-after.json', production_jobs())
    analyze(folder, args.commit, checkout)


if __name__ == '__main__':
    main()
