"""Analyse retained HTTP metadata and frozen sources, without running or changing tests."""

import bisect
import hashlib
import json
from collections import Counter

from nas_ssh import ROOT

FOLDER = ROOT / 'test-results/nas-parity/followup/frozen-soak-http-0ad540dd5780-attempt-3'
CHECKOUT = ROOT / '.sources/frozen-master/graphato-0ad540dd5780'


def density(rows):
    minimum = float('inf')
    minimum_index = 0
    best = {'demand_minus_refill': 0}
    for index, row in enumerate(rows):
        # Requests in [start, end] minus the original 100/second refill.
        preceding = index - row['started_ms'] / 10
        if preceding < minimum:
            minimum, minimum_index = preceding, index
        excess = index + 1 - row['started_ms'] / 10 - minimum
        if excess > best['demand_minus_refill']:
            selected = rows[minimum_index:index + 1]
            best = {'demand_minus_refill': round(excess, 3),
                    'requests': len(selected), 'duration_ms': round(row['started_ms'] - selected[0]['started_ms'], 3),
                    'commands': dict(Counter(r.get('command') or r['route'] for r in selected))}
    best['excess_over_original_burst'] = round(best['demand_minus_refill'] - 200, 3)
    return best


def main():
    target = FOLDER / 'read-amplification-analysis.json'
    assert not target.exists(), 'Retain the first source/timing analysis'
    path = FOLDER / 'leroy-artifacts/probe/http-metadata.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    starts = [r for r in rows if r['kind'] == 'request-start']
    ends = [r for r in rows if r['kind'] == 'request']
    successful_events = sorted(r['completed_ms'] for r in ends if r['route'] == '/api/v1/events' and r.get('status') == 200)
    providers = sorted((r for r in starts if r.get('command') == 'listProviderInstallations'), key=lambda r: r['started_ms'])
    intervals = [b['started_ms'] - a['started_ms'] for a, b in zip(providers, providers[1:], strict=False)]
    lags = []
    for row in providers:
        index = bisect.bisect_right(successful_events, row['started_ms']) - 1
        if index >= 0:
            lags.append(row['started_ms'] - successful_events[index])
    first_rejection = min(r['started_ms'] for r in ends if r.get('status') == 429)
    unauthenticated = {r['request_id'] for r in ends if r.get('status') == 401}
    credential_starts = sorted((r for r in starts if r['route'] in {'/api/v1/commands', '/api/v1/events', '/api/v1/info'}
                               and r['request_id'] not in unauthenticated and r['started_ms'] <= first_rejection),
                              key=lambda r: r['started_ms'])
    source_paths = ['apps/desktop/src/lib/platform/browserRuntime.ts',
                    'apps/desktop/src/lib/stores/providerInstallationStore.ts',
                    'apps/desktop/src/lib/components/onboarding/setupPolling.ts',
                    'apps/desktop/src/lib/stores/sessionPromptQueueStore.ts',
                    'apps/desktop/src-tauri/src/server/rate_limit.rs',
                    'apps/desktop/src-tauri/src/host.rs']
    value = {'metadata_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
             'frozen_source_sha256': {name: hashlib.sha256((CHECKOUT / name).read_bytes()).hexdigest() for name in source_paths},
             'provider_reads': len(providers), 'successful_event_responses': len(successful_events),
             'provider_start_intervals': {f'under_{limit}_ms': sum(delta < limit for delta in intervals) for limit in [100, 1000, 2000]},
             'provider_starts_after_an_event_completion': {f'within_{limit}_ms': sum(0 <= delta <= limit for delta in lags) for limit in [5, 10, 50, 100]},
             'before_first_429_client_start_density': density(credential_starts),
             'same_recorded_trace_with_provider_reads_excluded_arithmetically': density([r for r in credential_starts if r.get('command') != 'listProviderInstallations']),
             'source_mechanism': [
                 'BrowserRuntime.publish increments the connection revision after each successful event batch.',
                 'providerInstallationStore includes that revision in its connection key and stops/starts its status poller on each change.',
                 'Stopping clears pending deduplication as well as the timer; the next start issues a new provider read immediately.',
                 'The same callback invalidates IPC in-flight read deduplication globally.',
                 'Queue change events request the prompt queue again in each subscribed tab.',
                 'All admitted browser/native/event requests share one credential token bucket: 100/second, burst 200.',
             ],
             'limitations': [
                 'This reuses a previously retained observer diagnosis, not an original acceptance run.',
                 'Observer overhead is not excluded; no new observer or test execution is performed.',
                 'Records identify a browser context, not an individual page; temporal matches do not prove a one-to-one callback mapping.',
                 'Client starts are not server admissions; parent fixture traffic and actual bucket state are not recorded.',
                 'Removing rows is an arithmetic comparison, not an executed application fix or a prediction that tests would pass.',
                 'The historical Jenkins/Leroy timing difference remains unproven.',
             ],
             'tests_modified': False, 'application_modified': False,
             'new_measurement_started': False, 'cause_of_engine_result_difference_proven': False}
    target.write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({key: value[key] for key in ['provider_reads', 'successful_event_responses',
                    'provider_start_intervals', 'provider_starts_after_an_event_completion',
                    'before_first_429_client_start_density', 'same_recorded_trace_with_provider_reads_excluded_arithmetically']}))


if __name__ == '__main__':
    main()
