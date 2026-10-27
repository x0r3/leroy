"""Collect a dispatched final sample after monitoring loss, without redispatching it."""

import argparse
import json
import re
import subprocess
import time

import compare_nas_original_soak as comparison
from nas_followup_support import inner, jenkins_api
from nas_gitea_target import idle
from nas_measurement_guard import finish


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--series', required=True)
    args = parser.parse_args()
    assert re.fullmatch('[a-z0-9][a-z0-9-]{0,31}', args.series)
    comparison.SERIES = args.series
    comparison.FOLDER = comparison.FOLDER.with_name(comparison.FOLDER.name + '-' + args.series)
    comparison.JOB += '-' + args.series
    folder = comparison.FOLDER
    assert folder.is_dir() and not (folder / 'analysis.json').exists()
    samples = json.loads((folder / 'progress.json').read_text())['samples']
    assert list(samples) == list(comparison.ORDER[:-1])
    case = comparison.ORDER[-1]
    destination = folder / case
    intent = json.loads((destination / 'dispatch-intent.json').read_text())
    dispatched = json.loads((destination / 'dispatch.json').read_text())
    number = dispatched['build_number']
    assert intent['engine'] == 'jenkins' and intent['case'] == case and intent['build_number'] == number
    events = folder / 'observation-recovery.jsonl'
    assert not events.exists(), 'Keep earlier observation recovery'

    def event(value):
        with events.open('a', encoding='utf-8') as output:
            output.write(json.dumps({'at_epoch': time.time(), **value}) + '\n')

    event({'existing_build_number': number, 'existing_job': comparison.JOB, 'new_test_dispatched': False})
    deadline = time.monotonic() + 4400
    while time.monotonic() < deadline:
        try:
            state = json.loads(jenkins_api('/job/' + comparison.JOB + '/api/json?tree=lastBuild[number,result,building]')['text'])['lastBuild']
            assert state['number'] == number, 'Do not collect a different dispatched build'
            if not state['building'] and state['result']:
                break
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            event({'monitoring_read_error': type(error).__name__})
        time.sleep(15)
    else:
        raise TimeoutError('Existing owned build remains uncollected; retain it')
    ci = comparison.collect_jenkins(number, destination)
    comparison.host_observation(destination)
    qualification = finish(destination, case, intent['production_guard_before'])
    value = comparison.analyze_case(destination / 'diagnostic', destination, case)
    value['quiet_production_window'] = qualification['native_jenkins_quiet_window_verified']
    value['ci_result'] = ci['result']
    assert ci['result'] == ('SUCCESS' if value['passed'] else 'FAILURE')
    samples[case] = value
    assert list(samples) == list(comparison.ORDER)
    assert len({v['runtime_image_id'] for v in samples.values()}) == 1
    assert len({v['worker_image_id'] for v in samples.values()}) == 1
    event({'existing_build_collected': True, 'new_test_dispatched': False, 'original_passed': value['passed']})
    comparison.save(folder / 'progress.json', {'complete': True, 'samples': samples})
    comparison.save(folder / 'analysis.json', {'fixed_order_complete': True, 'samples': samples,
                                              'quiet_production_windows_all': all(v['quiet_production_window'] for v in samples.values()),
                                              'same_immutable_runtime_and_worker': True, 'unchanged_test_source_and_limits': True,
                                              'monitoring_recovered_without_test_redispatch': True,
                                              'complete_original_pipeline_acceptance': False, 'production_ready': False,
                                              'historical_difference_root_cause_proven': False, 'equal_background_load_proven': False})
    idle()
    before = json.loads((folder / 'jenkins-controller-before.json').read_text())
    current = json.loads(inner('inspect', 'jenkins-parity'))[0]
    assert current['Id'] == before['id']
    if not before['running']:
        inner('stop', '--time', '45', current['Id'], timeout=75)
        comparison.save(folder / 'jenkins-controller-restored.json', {'id': current['Id'], 'running': False,
                                                                     'controller_configuration_restored': True,
                                                                     'all_samples_same_controller_baseline': False})
    assert not inner('ps', '-q', '--filter', 'label=io.graphato.e2e.owner').strip()
    comparison.remove_temporary_profile()
    print(json.dumps({'series': args.series, 'fixed_order_complete': True, 'new_test_dispatched': False,
                      'samples': {k: v['ci_result'] for k, v in samples.items()}}), flush=True)


if __name__ == '__main__':
    main()
