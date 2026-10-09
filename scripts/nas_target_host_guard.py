"""Keep diagnostic VM work apart from unrelated Docker Desktop compilations."""

import json
import re
import subprocess
import time
from datetime import datetime, timezone


def state():
    output = subprocess.check_output(['docker', 'ps', '--format', '{{json .}}'], text=True)
    jobs = []
    for line in output.splitlines():
        row = json.loads(line)
        labels = dict(pair.split('=', 1) for pair in row['Labels'].split(',') if '=' in pair)
        service = labels.get('com.docker.compose.service', '')
        if re.search(r'(^|[-_])(tests?|test-runner)([-_]|$)', service):
            jobs.append({'container': row['ID'], 'name': row['Names'], 'service': service})
    output = subprocess.check_output(['wsl', '-d', 'docker-desktop', '--', 'ps', '-eo', 'pid,comm,rss'], text=True)
    processes = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[1] in {'rustc', 'cargo', 'cargo-clippy', 'clippy-driver', 'cc1plus', 'ld.lld'}:
            processes.append({'pid': int(fields[0]), 'name': fields[1], 'rss': fields[2]})
    memory = {}
    output = subprocess.check_output(['wsl', '-d', 'docker-desktop', '--', 'cat', '/proc/meminfo'], text=True)
    for line in output.splitlines():
        fields = line.split()
        if fields[0].rstrip(':') in {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'}:
            memory[fields[0].rstrip(':') + '_kib'] = int(fields[1])
    output = subprocess.check_output(['wsl', '-d', 'docker-desktop', '--', 'dmesg'], text=True)
    assert len(output) < 4 * 1024**2
    oom = [line for line in output.splitlines() if re.search(r'oom-kill:|Out of memory: Killed process|Memory cgroup out of memory:', line)]
    return {'at': datetime.now(timezone.utc).isoformat(), 'external_test_containers': jobs,
            'external_compilation_processes': processes, 'docker_desktop_memory': memory,
            'kernel_oom_events': oom, 'read_only': True, 'external_workloads_modified': False}


def begin(folder, phase, *, required_available_gib=0):
    assert re.fullmatch('[a-z0-9-]{1,40}', phase)
    deadline = time.monotonic() + 7200
    previous = None
    while time.monotonic() < deadline:
        value = state()
        available = value['docker_desktop_memory']['MemAvailable_kib']
        active = value['external_test_containers'] or value['external_compilation_processes']
        summary = {'external_tests': [row['name'] for row in value['external_test_containers']],
                   'external_compilers': [row['name'] for row in value['external_compilation_processes']],
                   'sufficient_memory': available >= required_available_gib * 1024**2}
        if summary != previous:
            print(json.dumps({'docker_desktop_guard': phase, **summary}), flush=True)
            previous = summary
        if not active and summary['sufficient_memory']:
            path = folder / ('target-host-before-' + phase + '.json')
            assert not path.exists(), 'Retain the first target-host observation'
            path.write_text(json.dumps(value, indent=2) + '\n')
            return value
        time.sleep(45)
    raise TimeoutError('External Docker Desktop tasks/headroom remain unsuitable; no diagnostic work started')


def finish(folder, phase, before):
    after = state()
    value = {'before': before, 'after': after,
             'no_external_test_or_compilation_at_boundaries': all(
                 not row['external_test_containers'] and not row['external_compilation_processes'] for row in (before, after)),
             'kernel_oom_events_unchanged': before['kernel_oom_events'] == after['kernel_oom_events'],
             'other_host_workloads_excluded': False, 'equal_background_load_proven': False,
             'external_workloads_modified': False}
    path = folder / ('target-host-qualification-' + phase + '.json')
    assert not path.exists(), 'Retain the first target-host qualification'
    path.write_text(json.dumps(value, indent=2) + '\n')
    return value
