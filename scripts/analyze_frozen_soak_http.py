"""Summarize request metadata without equating client starts with server admission."""

import argparse
import hashlib
import json
import re
from collections import Counter

from nas_ssh import ROOT


def peak_window(rows, duration_ms):
    times = sorted(row['started_ms'] for row in rows)
    left = 0
    best = {'requests': 0, 'window_ms': duration_ms, 'started_ms': None}
    for right, time in enumerate(times):
        while times[left] <= time - duration_ms:
            left += 1
        if right - left + 1 > best['requests']:
            best.update(requests=right - left + 1, started_ms=times[left])
    return best


def densest_budget_window(rows, refill_per_second=100, burst=200):
    """Client-start density only; elapsed network/server time is not observed."""
    times = sorted(row['started_ms'] for row in rows)
    best = {'demand_minus_refill': 0, 'excess_over_burst': 0}
    prefix = None
    for right, time in enumerate(times):
        candidate = refill_per_second * time / 1000 - right
        if prefix is None or candidate > prefix[0]:
            prefix = candidate, right
        left = prefix[1]
        demand = right - left + 1 - refill_per_second * (time - times[left]) / 1000
        if demand > best['demand_minus_refill']:
            best = {'demand_minus_refill': round(demand, 3), 'excess_over_burst': round(max(0, demand - burst), 3),
                    'requests': right - left + 1, 'started_ms': times[left], 'ended_ms': time,
                    'duration_ms': round(time - times[left], 3)}
    return best


def analyze(folder, destination):
    result_path, = (folder / 'leroy-artifacts').rglob('result.json')
    metadata_path, = (folder / 'leroy-artifacts').rglob('http-metadata.jsonl')
    result = json.loads(result_path.read_text())
    data = metadata_path.read_bytes()
    assert len(data) < 32 * 1024**2
    rows = [json.loads(line) for line in data.splitlines()]
    assert rows[0]['kind'] == 'diagnostic-start'
    assert rows[-1]['kind'] == 'diagnostic-end' and rows[-1]['dropped'] == 0
    starts = [row for row in rows if row['kind'] == 'request-start']
    complete = [row for row in rows if row['kind'] == 'request']
    ids = {row['request_id'] for row in starts}
    assert len(ids) == len(starts) and all(row['request_id'] in ids for row in complete)
    assert result['result']['cleanupComplete'] and not result['result']['reused']
    limited = [row for row in starts if row['route'] in {'/api/v1/commands', '/api/v1/events', '/api/v1/info'}]
    failures = sorted((row for row in complete if row['status'] == 429), key=lambda row: row['started_ms'])
    first = failures[0] if failures else None
    value = {
        'commit': result['commit'],
        'observer_image_proof': result['image_proof'],
        'metadata_sha256': hashlib.sha256(data).hexdigest(),
        'origin_metadata_sha256': result['http_metadata_sha256'],
        'metadata_json_formatting_changed_during_transport': True,
        'request_starts': len(starts), 'completed_request_records': len(complete),
        'unique_completed_requests': len({row['request_id'] for row in complete}),
        'requests_without_terminal_record': len(ids - {row['request_id'] for row in complete}),
        'by_client': dict(Counter(row['client'] for row in starts)),
        'by_route': dict(Counter(row['route'] for row in starts)),
        'by_command': dict(Counter(row['command'] for row in starts if row['command'])),
        'status_counts': dict(Counter(str(row['status']) for row in complete)),
        'credential_route_peak_windows': [peak_window(limited, duration) for duration in (100, 1000, 2000)],
        'client_start_density_at_original_defaults': densest_budget_window(limited),
        'default_budget_source': 'Frozen server/rate_limit.rs: 6000/minute, burst 200; values not changed',
        'http_429_requests': len(failures), 'first_429': first,
        'first_429_preceding_starts': ({str(duration): sum(
            first['started_ms'] - duration < row['started_ms'] <= first['started_ms']
            for row in limited) for duration in (100, 1000, 2000)} if first else {}),
        'original_soak_requested_passed': result['result']['requestedPassed'],
        'scope': 'Browser worker and native calls inside open-runner only; parent fixture traffic is not observed',
        'client_start_equals_server_admission': False,
        'observer_timing_overhead_excluded': False,
        'application_source_changed': False, 'application_rate_limits_changed': False,
        'original_acceptance_result_replaced': False, 'production_replacement_ready': False,
    }
    assert not destination.exists(), 'Preserve prior analysis'
    destination.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value[key] for key in ('request_starts', 'http_429_requests',
                                                'credential_route_peak_windows', 'first_429')}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--attempt', type=int, choices=[1, 2, 3], default=1)
    args = parser.parse_args()
    assert re.fullmatch('[a-f0-9]{40}', args.commit)
    folder = ROOT / ('test-results/nas-parity/followup/frozen-soak-http-' + args.commit[:12])
    if args.attempt > 1:
        folder = folder.with_name(folder.name + '-attempt-' + str(args.attempt))
    analyze(folder, folder / 'http-analysis.json')


if __name__ == '__main__':
    main()
