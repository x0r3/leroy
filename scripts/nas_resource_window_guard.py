"""NAS-side journal and recovery guard for one explicitly authorized window.

Only seven reviewed application containers can be paused. The watchdog lives
on the NAS so loss of the Windows SSH session does not leave them stopped.
"""

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path

try:
    import fcntl
except ModuleNotFoundError:
    # Planning can validate the pure policy on Windows; execution needs Linux.
    fcntl = None

ROOT = Path('/volume1/docker/leroy-nas-parity')
ALLOWED = {'paperless', 'sonarr', 'radarr', 'sabnzbd', 'plex',
           'yt-downloader-service', 'mail-ingest-service'}
ROUNDS = {'resource-window-clippy-leroy-20261013', 'resource-window-clippy-jenkins-20261013'}
ROUNDS |= {'resource-window-clippy-leroy-20261013-b', 'resource-window-clippy-jenkins-20261013-b'}
FULL_RELEASE_ROUND = 'full-release-controller512-20261013'
RECONCILE_RELEASE_ROUND = 'full-release-reconcile8g-20261014'
CAPACITY_WINDOW = 'resource-window-capacity-order0-20261014'
CAPACITY_ROUND = 'capacity-window-order0-20261014'
NIGHT_WINDOW = 'resource-window-night-20261014'
NIGHT_ROUNDS = ['night-capacity3584-20261014', 'night-capacity3840-20261014',
                'night-capacity4096-20261014', 'night-rust-leroy-20261014',
                'night-rust-jenkins-20261014', 'night-release-20261014']
ORIGINAL_NIGHT_WINDOW = 'resource-window-original-night-20261014'
ORIGINAL_NIGHT_ROUNDS = ['original-night-rust-leroy-20261014', 'original-night-rust-jenkins-20261014',
                         'original-night-release-20261014']
NIGHT_WINDOWS = {NIGHT_WINDOW: NIGHT_ROUNDS, ORIGINAL_NIGHT_WINDOW: ORIGINAL_NIGHT_ROUNDS}
NIGHT_WINDOWS[ORIGINAL_NIGHT_WINDOW + '-b'] = [name.replace('original-night-', 'original-night-b-')
                                             for name in ORIGINAL_NIGHT_ROUNDS]
NIGHT_WINDOWS[ORIGINAL_NIGHT_WINDOW + '-c'] = [name.replace('original-night-', 'original-night-c-')
                                             for name in ORIGINAL_NIGHT_ROUNDS]
NIGHT_WINDOWS[ORIGINAL_NIGHT_WINDOW + '-d'] = [name.replace('original-night-', 'original-night-d-')
                                             for name in ORIGINAL_NIGHT_ROUNDS]
NIGHT_WINDOWS[ORIGINAL_NIGHT_WINDOW + '-e'] = ['original-night-e-release-20261014']
NIGHT_WINDOWS[ORIGINAL_NIGHT_WINDOW + '-f'] = ['original-night-e-release-20261014']
DAY_WINDOWS = {
 'resource-window-day-20261015-rust-leroy': ['day-rust-leroy-20261015'],
 'resource-window-day-20261015-rust-jenkins': ['day-rust-jenkins-20261015'],
 'resource-window-day-20261015-release-leroy': ['day-release-20261015'],
 'resource-window-day-20261015-release-jenkins': ['day-release-20261015'],
}
DAY_WINDOWS.update({
 'resource-window-day-20261015-b-rust-leroy': ['day-b-rust-leroy-20261015'],
 'resource-window-day-20261015-b-rust-jenkins': ['day-b-rust-jenkins-20261015'],
 'resource-window-day-20261015-b-release-leroy': ['day-b-release-20261015'],
 'resource-window-day-20261015-b-release-jenkins': ['day-b-release-20261015'],
})
DAY_END = 1792101599  # 2026-10-15 23:59:59 Europe/Berlin
CONTINUATION_END = 1792187999  # Additional explicit authorization through 2026-10-16.
DAY_WINDOWS.update({
 'resource-window-day-20261015-c-rust-leroy': ['day-c-rust-leroy-20261015'],
 'resource-window-day-20261015-c-rust-jenkins': ['day-c-rust-jenkins-20261015'],
 'resource-window-day-20261015-c-release-leroy': ['day-c-release-20261015'],
 'resource-window-day-20261015-c-release-jenkins': ['day-c-release-20261015'],
})
DAY_WINDOWS.update({
 'resource-window-day-20261015-d-rust-leroy': ['day-d-rust-leroy-20261015'],
 'resource-window-day-20261015-d-rust-jenkins': ['day-d-rust-jenkins-20261015'],
 'resource-window-day-20261015-d-release-leroy': ['day-d-release-20261015'],
 'resource-window-day-20261015-d-release-jenkins': ['day-d-release-20261015'],
})
DAY_WINDOWS.update({
 'resource-window-day-20261015-e-rust-leroy': ['day-e-rust-leroy-20261015'],
 'resource-window-day-20261015-e-rust-jenkins': ['day-e-rust-jenkins-20261015'],
 'resource-window-day-20261015-e-release-leroy': ['day-e-release-20261015'],
 'resource-window-day-20261015-e-release-jenkins': ['day-e-release-20261015'],
})
DAY_WINDOWS.update({
 'resource-window-day-20261015-f-rust-leroy': ['day-f-rust-leroy-20261015'],
 'resource-window-day-20261015-f-rust-jenkins': ['day-f-rust-jenkins-20261015'],
 'resource-window-day-20261015-f-release-leroy': ['day-f-release-20261015'],
 'resource-window-day-20261015-f-release-jenkins': ['day-f-release-20261015'],
})
DAY_WINDOWS.update({
 'resource-window-day-20261015-g-rust-leroy': ['day-g-rust-leroy-20261015'],
 'resource-window-day-20261015-g-rust-jenkins': ['day-g-rust-jenkins-20261015'],
 'resource-window-day-20261015-g-release-leroy': ['day-g-release-20261015'],
 'resource-window-day-20261015-g-release-jenkins': ['day-g-release-20261015'],
})
DAY_WINDOWS.update({
 'resource-window-day-20261015-h-rust-leroy': ['day-h-rust-leroy-20261015'],
 'resource-window-day-20261015-h-rust-jenkins': ['day-h-rust-jenkins-20261015'],
 'resource-window-day-20261015-h-release-leroy': ['day-h-release-20261015'],
 'resource-window-day-20261015-h-release-jenkins': ['day-h-release-20261015'],
})
DAY_WINDOWS.update({
 'resource-window-day-20261015-i-rust-leroy': ['day-i-rust-leroy-20261015'],
 'resource-window-day-20261015-i-rust-jenkins': ['day-i-rust-jenkins-20261015'],
 'resource-window-day-20261015-i-release-leroy': ['day-i-release-20261015'],
 'resource-window-day-20261015-i-release-jenkins': ['day-i-release-20261015'],
})
DAY_WINDOWS.update({
 'resource-window-day-20261015-j-rust-leroy': ['day-j-rust-leroy-20261015'],
 'resource-window-day-20261015-j-rust-jenkins': ['day-j-rust-jenkins-20261015'],
 'resource-window-day-20261015-j-release-leroy': ['day-j-release-20261015'],
 'resource-window-day-20261015-j-release-jenkins': ['day-j-release-20261015'],
})
DAY_WINDOWS.update({
 'resource-window-day-20261015-k-rust-leroy': ['day-k-rust-leroy-20261015'],
 'resource-window-day-20261015-k-rust-jenkins': ['day-k-rust-jenkins-20261015'],
 'resource-window-day-20261015-k-release-leroy': ['day-k-release-20261015'],
 'resource-window-day-20261015-k-release-jenkins': ['day-k-release-20261015'],
})
DAY_WINDOWS.update({
 'resource-window-day-20261015-l-rust-leroy': ['day-l-rust-leroy-20261015'],
 'resource-window-day-20261015-l-rust-jenkins': ['day-l-rust-jenkins-20261015'],
 'resource-window-day-20261015-l-release-leroy': ['day-l-release-20261015'],
 'resource-window-day-20261015-l-release-jenkins': ['day-l-release-20261015'],
})
CONTINUATION_WINDOWS = {
 'resource-window-day-20261015-m-rust-leroy': ['day-m-rust-leroy-20261015'],
 'resource-window-day-20261015-m-rust-jenkins': ['day-m-rust-jenkins-20261015'],
 'resource-window-day-20261015-m-release-leroy': ['day-m-release-20261015'],
 'resource-window-day-20261015-m-release-jenkins': ['day-m-release-20261015'],
 'resource-window-day-20261015-n-rust-leroy': ['day-n-rust-leroy-20261015'],
 'resource-window-day-20261015-n-rust-jenkins': ['day-n-rust-jenkins-20261015'],
 'resource-window-day-20261015-n-release-leroy': ['day-n-release-20261015'],
 'resource-window-day-20261015-n-release-jenkins': ['day-n-release-20261015'],
 'resource-window-day-20261015-o-rust-leroy': ['day-o-rust-leroy-20261015'],
 'resource-window-day-20261015-o-rust-jenkins': ['day-o-rust-jenkins-20261015'],
 'resource-window-day-20261015-o-release-leroy': ['day-o-release-20261015'],
 'resource-window-day-20261015-o-release-jenkins': ['day-o-release-20261015'],
 'resource-window-day-20261015-p-rust-leroy': ['day-p-rust-leroy-20261015'],
 'resource-window-day-20261015-p-rust-jenkins': ['day-p-rust-jenkins-20261015'],
 'resource-window-day-20261015-p-release-leroy': ['day-p-release-20261015'],
 'resource-window-day-20261015-p-release-jenkins': ['day-p-release-20261015'],
}
for attempt in ('q', 'r', 's', 't', 'u'):
    for phase in ('rust-leroy', 'rust-jenkins', 'release-leroy', 'release-jenkins'):
        window = 'resource-window-day-20261015-' + attempt + '-' + phase
        round_name = ('day-' + attempt + '-' + phase + '-20261015' if phase.startswith('rust-')
                      else 'day-' + attempt + '-release-20261015')
        CONTINUATION_WINDOWS[window] = [round_name]
DAY_WINDOWS.update(CONTINUATION_WINDOWS)
OPEN_WINDOWS = {
    'resource-window-acceptance-20261017-' + attempt + '-' + phase:
    ['acceptance-20261017-' + attempt + '-' + phase if phase.startswith('rust-') else 'acceptance-20261017-' + attempt + '-release']
    for attempt in ('v', 'w', 'x', 'y')
    for phase in ('rust-leroy', 'rust-jenkins', 'release-leroy', 'release-jenkins')
    if (attempt != 'x' or phase.startswith('release-')) and (attempt != 'y' or phase == 'rust-jenkins')
}
DAY_WINDOWS.update(OPEN_WINDOWS)
FULL_RELEASE_COMPARISONS = {
 'resource-window-full-leroy-20261013': FULL_RELEASE_ROUND,
 'resource-window-full-jenkins-20261013': FULL_RELEASE_ROUND,
 'resource-window-reconcile8g-leroy-20261014': RECONCILE_RELEASE_ROUND,
 'resource-window-reconcile8g-jenkins-20261014': RECONCILE_RELEASE_ROUND,
}
FULL_RELEASE_WINDOWS = set(FULL_RELEASE_COMPARISONS)
COMMIT = '0ad540dd578033d45e4d0c25d89fbe57b32102a4'
DATA = Path(__file__).resolve().parent


def command(args, timeout=20):
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Command failed; output withheld')
    return result.stdout


def save(name, value):
    path = DATA / name
    temporary = DATA / (name + '.partial')
    with temporary.open('w', encoding='utf-8') as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    fd = os.open(DATA, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def read():
    return json.loads((DATA / 'state.json').read_text())


def inspect(identity, prefix=None):
    return json.loads(command((prefix or ['docker']) + ['inspect', identity]))[0]


def fingerprint(info):
    value = {key: info[key] for key in ('Id', 'Name', 'Image', 'Config', 'HostConfig', 'Mounts')}
    value['Mounts'] = sorted(value['Mounts'], key=lambda m: json.dumps(m, sort_keys=True))
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def reviewed(row):
    assert row['name'] in ALLOWED and re.fullmatch('[a-f0-9]{64}', row['id'])
    info = inspect(row['id'])
    assert info['Id'] == row['id'] and info['Name'] == '/' + row['name']
    assert fingerprint(info) == row['configuration_sha256'], 'Reviewed container changed'
    return info


def production_counters(state):
    home = Path(state['production_home']).resolve(strict=True)
    result = {}
    for name in state['production_counters']:
        directory = (home / 'jobs' / name).resolve(strict=True)
        assert directory.is_relative_to(home)
        counter = directory / 'nextBuildNumber'
        result[name] = int(counter.read_text()) - 1 if counter.is_file() else 0
    return result


def window_policy(plan, name):
    maximum = plan['maximum_window_seconds']
    if name in OPEN_WINDOWS:
        case, = OPEN_WINDOWS[name]
        assert maximum == (43200 if '-x-' in name else 14400) and plan['user_approved'] is True
        assert plan['comparison_rounds'] == [case] and plan['source_commit'] == COMMIT
        assert plan['explicit_user_request'] == 'Das Wartungsfenster ist nun unbegrenzt offen. Fahre fort wie vorgeschlagen'
        grant = plan['continuation_authorization']
        assert grant['open_ended'] is True and grant['closed_windows_extended'] is False
        assert re.fullmatch('[a-f0-9]{64}', grant['authorization_sha256'])
        assert time.time() + 1800 < plan['absolute_deadline_epoch'] <= time.time() + maximum
        return maximum, [case], 900
    if name in DAY_WINDOWS:
        assert maximum == 4 * 3600 and plan['user_approved'] is True
        assert plan['comparison_rounds'] == DAY_WINDOWS[name] and plan['source_commit'] == COMMIT
        assert isinstance(plan['explicit_user_request'], str) and plan['explicit_user_request'].strip()
        end = CONTINUATION_END if name in CONTINUATION_WINDOWS else DAY_END
        if name in CONTINUATION_WINDOWS:
            assert plan['explicit_user_request'] == 'Zwischenhinweis, dein Arbeitsfenster ist noch für den gesamten morgigen Tag freigegeben'
        assert time.time() + 1800 < plan['absolute_deadline_epoch'] <= min(end, time.time() + maximum)
        return maximum, DAY_WINDOWS[name][:], 900
    if name in NIGHT_WINDOWS:
        assert maximum == 10 * 3600 and plan['user_approved'] is True
        assert plan['comparison_rounds'] == NIGHT_WINDOWS[name]
        assert plan['source_commit'] == COMMIT
        assert isinstance(plan['explicit_user_request'], str) and plan['explicit_user_request'].strip()
        assert type(plan['absolute_deadline_epoch']) in (int, float)
        assert time.time() + 1800 < plan['absolute_deadline_epoch'] <= time.time() + maximum
        return maximum, NIGHT_WINDOWS[name][:], 900
    if name == CAPACITY_WINDOW:
        assert maximum == 3600 and plan['user_approved'] is True
        assert plan['comparison_round'] == CAPACITY_ROUND
        assert plan['synthetic_only'] is True and plan['original_ci_dispatched'] is False
        return maximum, [CAPACITY_ROUND], 900
    if name in FULL_RELEASE_WINDOWS:
        assert maximum == 14400 and plan['user_approved'] is True
        assert plan['comparison_round'] == FULL_RELEASE_COMPARISONS[name]
        rounds = [FULL_RELEASE_COMPARISONS[name]]
        if plan['comparison_round'] == RECONCILE_RELEASE_ROUND:
            assert plan['engine'] in {'leroy', 'jenkins'}
            expected = RECONCILE_RELEASE_ROUND + '-rust-' + plan['engine']
            assert plan['rust_qualification_round'] == expected
            rounds.append(expected)
    else:
        assert name == 'resource-window-20261013' and maximum == 7200
        rounds = sorted(ROUNDS)
    return maximum, rounds, 900 if maximum == 14400 else 300


def prepare():
    assert not (DATA / 'state.json').exists(), 'Retain the existing window journal'
    plan = json.loads((DATA / 'plan.json').read_text())
    assert {r['name'] for r in plan['containers']} == ALLOWED and len(plan['containers']) == 7
    maximum, rounds, margin = window_policy(plan, DATA.name)
    assert plan['graceful_stop_seconds'] == 120
    vm = inspect('leroy-nas-release-target-vm')
    assert not vm['State']['Running']
    outer = inspect('leroy-nas-parity-docker-1')
    assert outer['Config']['Labels']['com.docker.compose.project'] == 'leroy-nas-parity'
    prefix = ['docker', 'exec', outer['Id'], 'docker']
    private = inspect('jenkins-parity', prefix)
    assert not private['State']['Running']
    native = inspect('jenkins')
    home = next(m['Source'] for m in native['Mounts'] if m['Destination'] == '/var/jenkins_home')
    state = {'prepared_at': time.time(), 'started_at': None, 'deadline': None, 'phase': 'prepared',
             'containers': [], 'runs': [], 'outer_daemon_id': outer['Id'],
             'private_jenkins_id': private['Id'], 'production_home': home,
             'production_counters': plan['production_counters'], 'events': [],
             'maximum_window_seconds': maximum, 'comparison_rounds': rounds,
             'restore_margin_seconds': margin}
    if DATA.name in NIGHT_WINDOWS or DATA.name in DAY_WINDOWS:
        state['absolute_deadline_epoch'] = plan['absolute_deadline_epoch']
    assert production_counters(state) == state['production_counters']
    for row in plan['containers']:
        assert re.fullmatch('[a-f0-9]{64}', row['id'])
        info = inspect(row['id'])
        assert info['Id'] == row['id'] and info['Name'] == '/' + row['name'] and info['State']['Running']
        save('before-' + row['name'] + '.json', info)
        state['containers'].append({'name': row['name'], 'id': row['id'],
                                    'configuration_sha256': fingerprint(info), 'phase': 'eligible',
                                    'before_health': info['State'].get('Health', {}).get('Status')})
    save('state.json', state)
    return state


def pause():
    state = read()
    assert state['phase'] == 'prepared' and production_counters(state) == state['production_counters']
    for row in state['containers']:
        assert reviewed(row)['State']['Running'], 'A reviewed service was stopped outside this window'
    now = time.time()
    if state['started_at'] is None:
        deadline = state.get('absolute_deadline_epoch', now + state.get('maximum_window_seconds', 7200))
        assert now + 1800 < deadline <= now + state.get('maximum_window_seconds', 7200)
        state.update(started_at=now, deadline=deadline)
    else:
        assert state['deadline'] == state.get('absolute_deadline_epoch',
                                            state['started_at'] + state.get('maximum_window_seconds', 7200))
        assert now < state['deadline'] - 1800, 'Preserve stopping and recovery time'
    state.update(phase='pausing', pause_cycle_started_at=now)
    save('state.json', state)
    for row in state['containers']:
        assert production_counters(state) == state['production_counters'], 'Production build counter changed'
        row.update(phase='stopping', stop_requested_at=time.time())
        save('state.json', state)
        command(['docker', 'stop', '--time', '120', row['id']], timeout=135)
        info = reviewed(row)
        assert not info['State']['Running']
        row.update(phase='stopped', stopped_at=time.time(), stopped_exit_code=info['State']['ExitCode'])
        save('state.json', state)
    state['phase'] = 'paused'
    save('state.json', state)
    return state


def reopen():
    """One evidence-led follow-up inside the original absolute two-hour limit."""
    state = read()
    assert state.get('maximum_window_seconds', 7200) == 7200, 'Full-release windows have separate journals'
    assert state['phase'] == 'restored' and state.get('attempt', 1) == 1
    assert state['deadline'] == state['started_at'] + 7200
    assert time.time() < state['deadline'] - 1800, 'Never grant another two hours'
    assert production_counters(state) == state['production_counters']
    assert not inspect('leroy-nas-release-target-vm')['State']['Running']
    prefix = ['docker', 'exec', state['outer_daemon_id'], 'docker']
    assert not inspect(state['private_jenkins_id'], prefix)['State']['Running']
    for row in state['containers']:
        info = reviewed(row)
        assert info['State']['Running'] and info['State'].get('Health', {}).get('Status') in (None, 'healthy')
        save('before-attempt-2-' + row['name'] + '.json', info)
    assert not (DATA / 'completed-attempt-1.json').exists()
    save('completed-attempt-1.json', state)
    for row in state['containers']:
        row['phase'] = 'eligible'
    state.update(attempt=2, phase='prepared')
    state['events'].append({'at': time.time(), 'kind': 'followup_with_original_absolute_deadline'})
    save('state.json', state)
    return state


def process_identity(pid):
    assert type(pid) is int and pid > 1
    root = Path('/proc') / str(pid)
    try:
        fields = (root / 'stat').read_text().rpartition(') ')[2].split()
        if fields[0] == 'Z':
            return None
        return {'start_ticks': fields[19], 'cgroup': (root / 'cgroup').read_text(),
                'command_sha256': hashlib.sha256((root / 'cmdline').read_bytes()).hexdigest()}
    except FileNotFoundError:
        return None


def remember_owned_vm(state):
    retained = state.get('owned_vm_process')
    if retained and process_identity(retained['pid']) == retained['identity']:
        return False
    try:
        vm = inspect('leroy-nas-release-target-vm')
    except RuntimeError:
        # Boot briefly removes the old container before creating its successor.
        # A successful empty listing proves absence; a failed API call must
        # still propagate instead of silently disabling recovery registration.
        identities = command(['docker', 'ps', '-aq', '--no-trunc', '--filter',
                              'name=^/leroy-nas-release-target-vm$']).split()
        if not identities:
            return False
        assert len(identities) == 1
        vm = inspect(identities[0])
    if not vm['State']['Running']:
        return False
    assert vm['Config']['Labels'].get('io.leroy.nas-release-target') == COMMIT
    assert vm['Config']['Labels'].get('io.leroy.comparison') in state.get('comparison_rounds', ROUNDS)
    identity = process_identity(vm['State']['Pid'])
    assert identity and re.fullmatch('[a-f0-9]{64}', vm['Id'])
    parts = [part for line in identity['cgroup'].splitlines() for part in line.split(':', 2)[-1].split('/')]
    assert vm['Id'] in parts or 'docker-' + vm['Id'] + '.scope' in parts
    state['owned_vm_process'] = {'container_id': vm['Id'], 'pid': vm['State']['Pid'], 'identity': identity}
    state.pop('owned_vm_stop_requested_at', None)
    return True


def direct_stop_owned_vm(state):
    """Stop only the recorded container init if the Docker API is unresponsive."""
    retained = state.get('owned_vm_process')
    assert retained, 'No verified process identity; never signal an unreviewed process'
    current = process_identity(retained['pid'])
    if current is None:
        return True
    assert current == retained['identity'], 'Recorded VM PID was reused or changed'
    if 'owned_vm_stop_requested_at' not in state:
        # The verified pin is already durable. Queue the idempotent signal
        # before another journal fsync can stall on the failing NAS storage.
        os.kill(retained['pid'], signal.SIGTERM)
        state['owned_vm_stop_requested_at'] = time.time()
        state['events'].append({'at': state['owned_vm_stop_requested_at'], 'kind': 'owned_vm_direct_graceful_stop'})
        save('state.json', state)
    elif time.time() - state['owned_vm_stop_requested_at'] >= (10 if state.get('host_reserve_stop') else 210):
        os.kill(retained['pid'], signal.SIGKILL)
        state['events'].append({'at': time.time(), 'kind': 'owned_vm_direct_forced_stop'})
        save('state.json', state)
    return False


def stop_owned_vm(state):
    if state.get('host_reserve_stop'):
        if not direct_stop_owned_vm(state):
            raise RuntimeError('Host reserve shutdown pending; do not restore applications over active test load')
        return
    try:
        vm = inspect('leroy-nas-release-target-vm')
        if vm['State']['Running']:
            labels = vm['Config']['Labels']
            assert labels.get('io.leroy.nas-release-target') == COMMIT
            assert labels.get('io.leroy.comparison') in state.get('comparison_rounds', ROUNDS)
            command(['docker', 'stop', '--time', '45', vm['Id']], timeout=60)
    except (RuntimeError, subprocess.TimeoutExpired):
        if not direct_stop_owned_vm(state):
            raise RuntimeError('Owned VM shutdown pending; do not restore applications over active test load') from None


def end_test_load(state):
    prefix = ['docker', 'exec', state['outer_daemon_id'], 'docker']
    for run in state['runs']:
        ids = command(prefix + ['ps', '-aq', '--filter', 'label=io.leroy.run=' + run]).split()
        for identity in ids:
            info = inspect(identity, prefix)
            assert info['Config']['Labels'].get('io.leroy.run') == run
            assert info['Config']['Labels'].get('io.leroy.runner') == 'runner-nas-parity'
            if info['State']['Running']:
                command(prefix + ['stop', '--time', '20', info['Id']], timeout=35)
    private = inspect(state['private_jenkins_id'], prefix)
    assert private['Name'] == '/jenkins-parity'
    if private['State']['Running']:
        command(prefix + ['stop', '--time', '60', private['Id']], timeout=75)


def restore(reason):
    state = read()
    if state['phase'] == 'restored':
        return state
    state['events'].append({'at': time.time(), 'kind': 'restore_requested', 'reason': reason})
    try:
        stop_owned_vm(state)
    except Exception as error:
        state['events'].append({'at': time.time(), 'kind': 'vm_stop_pending', 'type': type(error).__name__})
        state['phase'] = 'restore_error'
        save('state.json', state)
        return state
    try:
        end_test_load(state)
    except Exception as error:
        state['events'].append({'at': time.time(), 'kind': 'test_stop_error', 'type': type(error).__name__})
        save('state.json', state)
    failures = []
    for row in reversed(state['containers']):
        if row['phase'] not in {'stopping', 'stopped', 'restore_error'}:
            continue
        try:
            info = reviewed(row)
            if not info['State']['Running']:
                command(['docker', 'start', row['id']], timeout=30)
            info = reviewed(row)
            assert info['State']['Running']
            row.update(phase='restored', restored_at=time.time(),
                       after_health=info['State'].get('Health', {}).get('Status'),
                       after_restart_count=info['RestartCount'])
        except Exception as error:
            row.update(phase='restore_error', error_type=type(error).__name__)
            failures.append(row['name'])
        save('state.json', state)
    state['phase'] = 'restore_error' if failures else 'restored'
    state['finished_at'] = time.time()
    save('state.json', state)
    return state


def reserve_violation(meminfo):
    values = {line.split(':')[0]: int(line.split()[1]) for line in meminfo.splitlines()}
    if values['MemAvailable'] < 128 * 1024:
        reason = 'host_available_reserve'
    elif values['SwapFree'] < 2304 * 1024:
        reason = 'host_swap_reserve'
    else:
        return None
    return {'reason': reason, 'available_kib': values['MemAvailable'], 'swap_free_kib': values['SwapFree']}


def watch():
    assert fcntl is not None, 'Recovery execution requires Linux file locks'
    while True:
        time.sleep(10)
        with (DATA / 'operation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = read()
            if state['phase'] == 'restored':
                return state
            if state['started_at'] is None:
                if time.time() > state['prepared_at'] + 1800:
                    return state
                continue
            reason = None
            retained = state.get('owned_vm_process')
            if retained and process_identity(retained['pid']) == retained['identity']:
                observation = reserve_violation(Path('/proc/meminfo').read_text())
                if observation:
                    state['host_reserve_stop'] = observation
                    direct_stop_owned_vm(state)
                    save('state.json', state)
                    reason = observation['reason']
            if reason:
                pass
            elif time.time() >= state['deadline'] - state.get('restore_margin_seconds', 300):
                reason = 'window_deadline_restore_margin'
            elif state['phase'] == 'restore_error':
                reason = 'retry_incomplete_restore'
            else:
                try:
                    if production_counters(state) != state['production_counters']:
                        reason = 'productive_build_counter_changed'
                except Exception:
                    reason = 'production_observation_unavailable'
            if reason:
                result = restore(reason)
                if result['phase'] == 'restored':
                    return result


def main():
    assert fcntl is not None, 'Recovery execution requires Linux file locks'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'pause', 'status', 'restore', 'watch', 'register', 'register-vm', 'reopen'))
    parser.add_argument('--run')
    args = parser.parse_args()
    assert os.geteuid() == 0 and DATA.parent == ROOT
    assert DATA.name in {'resource-window-20261013', CAPACITY_WINDOW, *NIGHT_WINDOWS, *DAY_WINDOWS, *FULL_RELEASE_WINDOWS}
    assert ROOT.resolve() == ROOT and (ROOT / '.leroy-owned').is_file()
    assert DATA.resolve() == DATA and not DATA.is_symlink() and DATA.stat().st_mode & 0o077 == 0
    if args.action == 'watch':
        result = watch()
    else:
        with (DATA / 'operation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if args.action == 'prepare':
                result = prepare()
            elif args.action == 'pause':
                result = pause()
            elif args.action == 'restore':
                result = restore('operator_finished_or_failed_diagnostic')
            elif args.action == 'reopen':
                result = reopen()
            elif args.action == 'register-vm':
                result = read()
                assert result['phase'] == 'paused'
                if remember_owned_vm(result):
                    save('state.json', result)
            elif args.action == 'register':
                assert args.run and re.fullmatch('[a-f0-9]{32}', args.run)
                result = read()
                assert result['phase'] == 'paused'
                if args.run not in result['runs']:
                    result['runs'].append(args.run)
                remember_owned_vm(result)
                save('state.json', result)
            else:
                result = read()
    print(json.dumps(result))


if __name__ == '__main__':
    main()
