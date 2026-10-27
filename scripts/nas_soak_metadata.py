"""Qualify passive HTTP evidence without treating absent responses as HTTP success."""

import argparse
import json
from pathlib import Path


def qualify(rows, observation):
    requests = {r['request_id']: r for r in rows if r['kind'] == 'request'}
    responses = [r for r in rows if r['kind'] == 'response' and r['status'] >= 200]
    matched = {r['request_id'] for r in responses if r.get('request_id') in requests}
    # Event streams can remain open until fixture cleanup. Finite requests must
    # have response evidence before the trace can establish HTTP-status absence.
    finite = {identity for identity, r in requests.items() if r['route'] != '/api/v1/events'}
    commands = {identity for identity, r in requests.items() if r['route'] == '/api/v1/commands'}
    prompts = {identity for identity, r in requests.items() if r.get('command') == 'sendSessionPrompt'}
    counts = observation.get('parser_counts') or {}
    transport = bool(requests and observation.get('started') and observation.get('ended_cleanly')
                     and observation.get('exit_code') == 0 and counts.get('kernel_packets_dropped') == 0
                     and not any(counts.get(k) for k in ('unparsed_streams', 'connection_bound_exceeded',
                                                       'incomplete_tcp_streams', 'truncated_packets')))
    qualified = transport and not (finite - matched)
    return {'server_boundary_metadata_qualified': qualified,
            'finite_requests_observed': len(finite), 'finite_responses_matched': len(finite & matched),
            'finite_requests_without_response': len(finite - matched),
            'command_requests_observed': len(commands), 'command_responses_matched': len(commands & matched),
            'prompt_requests_observed': len(prompts), 'prompt_responses_matched': len(prompts & matched),
            'observed_http_429_responses': sum(r['status'] == 429 for r in responses),
            'absence_of_http_429_established': qualified and not any(r['status'] == 429 for r in responses),
            'all_request_capture_proven': False, 'actual_rate_limiter_admission_times_observed': False}


def self_check():
    observation = {'started': True, 'ended_cleanly': True, 'exit_code': 0,
                   'parser_counts': {'kernel_packets_dropped': 0}}
    rows = [{'kind': 'request', 'request_id': 1, 'route': '/api/v1/commands', 'command': 'sendSessionPrompt'},
            {'kind': 'request', 'request_id': 2, 'route': '/api/v1/health'},
            {'kind': 'response', 'request_id': 2, 'status': 200}]
    partial = qualify(rows, observation)
    assert not partial['server_boundary_metadata_qualified'] and not partial['absence_of_http_429_established']
    assert partial['prompt_responses_matched'] == 0
    rows.append({'kind': 'response', 'request_id': 1, 'status': 429})
    complete = qualify(rows, observation)
    assert complete['server_boundary_metadata_qualified'] and complete['observed_http_429_responses'] == 1
    assert not complete['absence_of_http_429_established']
    rows[-1]['status'] = 200
    assert qualify(rows, observation)['absence_of_http_429_established']
    observation['parser_counts']['kernel_packets_dropped'] = 1
    assert not qualify(rows, observation)['server_boundary_metadata_qualified']
    print('HTTP evidence qualification checks passed; incomplete answers remain unqualified.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--series-folder', type=Path)
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return
    assert args.series_folder
    folder = args.series_folder.resolve(strict=True)
    root = Path(__file__).resolve().parents[1] / 'test-results'
    assert folder.is_relative_to(root.resolve())
    original = json.loads((folder / 'analysis.json').read_text())
    assert original['fixed_order_complete']
    output = folder / 'metadata-qualification.json'
    assert not output.exists(), 'Keep earlier diagnostic qualifications'
    samples = {}
    for case, value in original['samples'].items():
        metadata = folder / case / 'original-artifacts/http-metadata.jsonl'
        rows = [json.loads(line) for line in metadata.read_text().splitlines()] if metadata.exists() else []
        samples[case] = qualify(rows, value['observation'])
    result = {'raw_artifacts_and_original_receipts_unchanged': True, 'samples': samples,
              'http_status_evidence_complete_all': all(v['server_boundary_metadata_qualified'] for v in samples.values())}
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
