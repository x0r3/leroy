"""Compare original recorded test outcomes, independently of group status.

Read only the already verified archives and retained comparison report. This
helper never contacts CI or the target and never reruns application tests.
"""

import argparse
import json
import re
import tarfile
from collections import Counter
from pathlib import PurePosixPath

import compare_nas_full_release as full
from nas_ssh import ROOT


def component_outcomes(data):
    proof = full.component_inventory(data)
    assert proof.get('complete_terminal_inventory'), 'Incomplete component log cannot establish parity'
    text = re.sub(r'\x1b\[[0-9;]*m', '', data.decode(errors='replace'))
    ends = list(re.finditer(r'^(?:ℹ|#) duration_ms [\d.]+\s*$', text, re.MULTILINE))
    start = ends[-2].end() if len(ends) > 1 else 0
    rows = re.findall(r'^([✔✖]) (.+?) \([\d.]+ms\)$', text[start:ends[-1].start()], re.MULTILINE)
    result = {name: 'passed' if mark == '✔' else 'failed' for mark, name in rows}
    assert len(rows) == len(result) == proof['counts']['tests']
    return result


def outcome_difference(jenkins, leroy):
    return [{'identity': name, 'jenkins': jenkins.get(name, 'missing'), 'leroy': leroy.get(name, 'missing')}
            for name in sorted(jenkins.keys() | leroy.keys()) if jenkins.get(name) != leroy.get(name)]


def rust_events(data):
    result = Counter()
    for line in data.decode(errors='replace').splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get('type') == 'test' and row.get('event') in {'ok', 'failed', 'ignored'}:
            result[row['name'], row['event']] += 1
    return result


def archive_logs(folder, engine):
    path, sha = full.artifact_path(folder / 'graphato-postdeploy-quality', engine, 'artifacts.tar.gz', folder)
    wanted = {'server-test.log', 'frontend-and-deployment.log'}
    result = {}
    total = 0
    names = set()
    with tarfile.open(path) as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            assert member.isfile() and not name.is_absolute() and '..' not in name.parts
            assert 0 <= member.size <= 64 * 1024**2 and member.name not in names and len(names) < 1000
            names.add(member.name)
            total += member.size
            assert total <= 256 * 1024**2
            if member.name in wanted:
                result[member.name] = archive.extractfile(member).read()
    assert wanted <= result.keys()
    return result, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', required=True)
    folder = (ROOT / parser.parse_args().folder).resolve()
    assert folder.is_relative_to(ROOT / 'test-results/nas-parity/followup')
    report = json.loads((folder / 'analysis.json').read_text(encoding='utf-8'))
    assert report['all_29_original_group_receipts_present_both']
    assert not report['application_source_changed'] and not report['application_tests_changed']
    results = {}
    for engine in ('jenkins', 'leroy'):
        logs, sha = archive_logs(folder, engine)
        quality = report['suites']['quality'][engine]
        assert sha == quality['archive_sha256']
        components = component_outcomes(logs['frontend-and-deployment.log'])
        assert len(components) == 98 and quality['same_full_component_inventory_as_original']
        browser = {}
        for group, row in report['suites']['web'][engine]['browser_case_results'].items():
            for case in row['original_results']:
                identity = case.get('id', case.get('name'))
                if identity is not None:
                    key = group + '/' + identity
                    assert key not in browser
                    browser[key] = 'passed' if case['passed'] else 'failed'
        rust = rust_events(logs['server-test.log'])
        python_counts = [int(n) for n in re.findall(r'\bRan (\d+) tests? in ', logs['frontend-and-deployment.log'].decode(errors='replace'))]
        python_ok = len(re.findall(r'^OK\s*$', logs['frontend-and-deployment.log'].decode(errors='replace'), re.MULTILINE))
        supplement = folder / (engine + '-supplementary-frontend.log')
        if supplement.exists():
            assert supplement.read_bytes() == logs['frontend-and-deployment.log'], 'Supplement differs from original CI archive'
        results[engine] = {'archive_sha256': sha, 'components': components, 'browser': browser,
                           'rust': rust, 'python_counts': python_counts, 'python_ok': python_ok}
    first, second = results['jenkins'], results['leroy']
    component_diff = outcome_difference(first['components'], second['components'])
    browser_diff = outcome_difference(first['browser'], second['browser'])
    rust_diff = [{'name': name, 'event': event, 'jenkins': first['rust'][name, event], 'leroy': second['rust'][name, event]}
                 for name, event in sorted(first['rust'].keys() | second['rust'].keys())
                 if first['rust'][name, event] != second['rust'][name, event]]
    python_complete = all(results[engine]['python_counts'] == report['original_quality_inventory_reference']['python_suite_test_counts']
                          and results[engine]['python_ok'] == len(results[engine]['python_counts'])
                          for engine in ('jenkins', 'leroy'))
    inventory_complete = all(report['suites']['quality'][engine]['complete_original_quality_test_inventories_proven']
                             and report['suites']['web'][engine]['all_original_browser_cases_executed']
                             for engine in ('jenkins', 'leroy'))
    value = {'commit': report['commit'], 'original_archive_sha256': {engine: results[engine]['archive_sha256'] for engine in results},
             'same_original_group_statuses_both': report['same_original_group_statuses_both'],
             'complete_original_inventories_both': inventory_complete,
             'component_differences': component_diff, 'browser_differences': browser_diff,
             'rust_named_event_multiset_differences': rust_diff,
             'python_all_original_suites_successful_both': python_complete,
             'same_recorded_named_outcomes_both': inventory_complete and python_complete and not component_diff and not browser_diff and not rust_diff,
             'component_failed_tests': {engine: [name for name, status in results[engine]['components'].items() if status == 'failed'] for engine in results},
             'rust_identity_scope': 'Original recorded names and event multiplicities; no invented binary identities',
             'application_source_changed': False, 'application_tests_changed': False, 'original_ci_restarted': False,
             'production_modified': False, 'production_replacement_ready': False}
    output = folder / 'original-test-outcome-comparison.json'
    assert not output.exists(), 'Retain the original comparison before rerunning analysis'
    output.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(value))


if __name__ == '__main__':
    main()
