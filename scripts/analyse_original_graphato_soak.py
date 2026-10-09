"""Compare retained original Soak receipts without executing or modifying tests."""

import hashlib
import json
import tarfile

from nas_ssh import ROOT

COMMIT = '0ad540dd578033d45e4d0c25d89fbe57b32102a4'
SOURCE = 'f0c737a8133cd73f6b34c66be5081316a7047a1881583532874b40abaec59708'
FOLLOWUP = ROOT / 'test-results/nas-parity/followup'
GROUPS = FOLLOWUP / 'candidates/graphato' / COMMIT / 'controlled-groups'


def sample(path, scope, engine):
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        assert len(members) < 2000 and sum(row.size for row in members) < 128 * 1024**2

        def read(name):
            member = archive.getmember(name)
            assert member.isfile() and member.size < 16 * 1024**2
            return archive.extractfile(member).read()

        case, = json.loads(read('browser-soak/open/results.json'))
        provenance = json.loads(read('browser-soak/provenance.json'))
        server = json.loads(read('browser-soak/server.json'))
        assert case['id'] == 'soak'
        assert provenance['runnerSource'] == {'commit': COMMIT, 'sourceArchiveSha256': SOURCE, 'dirty': False}
        assert server['sourceCommit'] == COMMIT
        metrics = []
        for line in read('browser-soak.log').decode(errors='replace').splitlines():
            try:
                value = json.loads(line[line.index('{'):])
            except ValueError:
                continue
            if isinstance(value, dict) and value.get('event') == 'boundedSoak':
                metrics.append(value)
        with path.open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        error = case.get('error', '')
        return {'scope': scope, 'engine': engine, 'archive': str(path.relative_to(ROOT)),
                'archive_sha256': checksum, 'passed': case['passed'], 'duration_ms': case['durationMs'],
                'failure_during_prompt_command': 'acceptance/sendSessionPrompt:' in error,
                'prompt_request_rate_limit_failure': 'request rate for this server credential is exceeded' in error,
                'bounded_soak_metrics': metrics, 'server_binary_sha256': server['serverSha256'],
                'runtime_image_id': provenance['runtimeImageId'], 'browser_worker_image_id': provenance['workerImageId'],
                'runtime_base_sha256': server['runtimeBaseSha256'], 'build': server['serverBuild'],
                'docker_host': server['dockerHost'], 'node_version': server['nodeVersion'],
                'server_rustc_version': server['serverRustcVersion'], 'postgres_image_id': server['postgresImageId'],
                'compose_sha256': server['composeSha256'], 'runtime_dockerfile_sha256': server['runtimeDockerfileSha256'],
                'fixture_bootstrap_sha256': server['fixtureBootstrapSha256'],
                'runner_source': provenance['runnerSource']}


def main():
    rows = [sample(FOLLOWUP / 'native-browser-observations/web-18/artifacts.tar.gz', 'original-production-web-18', 'jenkins')]
    for group in ['web-soak-round-1', 'web-soak-cpu-eight-round-1', 'web-soak-cpu-eight-round-2']:
        paths = sorted((GROUPS / group).rglob('artifacts.tar.gz'))
        assert len(paths) == 2
        for path in paths:
            engine = 'jenkins' if any(part.startswith('jenkins-') for part in path.parts) else 'leroy'
            rows.append(sample(path, group, engine))
    path, = (GROUPS / 'full-release-leroy-cpu-eight-round-1/graphato-postdeploy-web').rglob('artifacts.tar.gz')
    rows.append(sample(path, 'full-release-leroy-cpu-eight-round-1', 'leroy'))
    common = {key: len({json.dumps(row[key], sort_keys=True) for row in rows}) == 1
              for key in ['runner_source', 'node_version', 'server_rustc_version', 'postgres_image_id',
                          'compose_sha256', 'runtime_dockerfile_sha256', 'fixture_bootstrap_sha256']}
    assert all(common.values())
    failed = [row for row in rows if not row['passed']]
    assert failed and all(row['failure_during_prompt_command'] and row['prompt_request_rate_limit_failure'] for row in failed)
    value = {'commit': COMMIT, 'source_archive_sha256': SOURCE, 'samples': rows, 'equal_recorded_inputs': common,
             'all_retained_original_soak_failures_are_prompt_rate_limits': True,
             'all_retained_original_soak_failures_precede_300_second_observation': all(row['duration_ms'] < 300_000 for row in failed),
             'same_isolated_runtime_has_both_success_and_failure': len({row['passed'] for row in rows[1:]}) == 2
                 and len({row['runtime_image_id'] for row in rows[1:]}) == 1,
             'native_and_isolated_runtime_images_equal': rows[0]['runtime_image_id'] == rows[1]['runtime_image_id'],
             'native_and_isolated_target_memory_equal': rows[0]['docker_host']['memoryBytes'] == rows[1]['docker_host']['memoryBytes'],
             'test_files_modified': False, 'application_files_modified': False, 'production_modified': False,
             'newer_production_commits_used_as_comparison': False, 'cause_of_engine_difference_proven': False,
             'original_acceptance_result_replaced': False, 'production_replacement_ready': False,
             'limits': ['Archived original results lack all HTTP request admission timestamps.',
                        'Matching version strings do not prove every worker image file is identical.',
                        'The native and isolated application hosts have different memory and runtime artifacts.',
                        'Historical success and failure are not a controlled single-variable causal experiment.']}
    destination = FOLLOWUP / 'native-browser-observations/web-18/original-test-comparison.json'
    assert not destination.exists(), 'Retain the first comparison of original archived tests'
    destination.write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({'samples': len(rows), 'passed': sum(row['passed'] for row in rows),
                      'failed': len(failed), 'equal_recorded_inputs': common,
                      'all_failures_are_prompt_rate_limits': True, 'tests_modified': False}), flush=True)


if __name__ == '__main__':
    main()
