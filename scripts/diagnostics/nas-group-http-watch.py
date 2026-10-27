"""Observe only original web fixtures inside the owned isolated Linux guest.

Run from a protected diagnostic directory with runtime.txt and observe.py.
Never persist packets, credentials, arbitrary container environments or logs.
"""

import hashlib
import json
import os
import pathlib
import subprocess
import time

work = pathlib.Path.cwd().resolve()
assert work.parent == pathlib.Path('/var/lib/leroy-diagnostics')
assert (work / '.leroy-owned').read_text() == 'Unchanged dev-environments diagnostic observer\n'
runtime = (work / 'runtime.txt').read_text().strip()
assert runtime == 'sha256:6251c60f499e41e706613f931bf281ce52312b957d5a6a123cf4e27dd3242585'
owner = 'io.leroy.group-observer=' + work.name
events, observers, seen = [], [], set()
started = time.time()
proxies, proxy_rows, proxy_seen = {}, [], set()
last_proxy_poll = 0
key=work/'identity-key'
with key.open('xb') as stream:
    stream.write(os.urandom(32))
key.chmod(0o600)


def call(args, timeout=15):
    return subprocess.check_output(['docker', *args], text=True, timeout=timeout).strip()


def event(kind, **value):
    row = {'kind': kind, 'at': time.time(), **value}
    events.append(row)
    with (work / 'events.jsonl').open('a') as stream:
        stream.write(json.dumps(row) + '\n')


try:
    while not (work / 'stop.flag').exists() and time.time() - started < 1200:
        ids = call(['ps', '-q', '--filter', 'label=io.graphato.e2e.owner', '--filter', 'label=com.docker.compose.service=server']).split()
        if time.time()-last_proxy_poll >= 2:
            last_proxy_poll = time.time()
            for identity in call(['ps','-q','--filter','label=io.graphato.e2e.owner','--filter','label=com.docker.compose.service=webproxy']).split():
                if identity not in proxies:
                    try:
                        proxy=json.loads(call(['inspect',identity]))[0]
                    except subprocess.CalledProcessError:
                        event('fixture-cleanup-race', service='webproxy')
                        continue
                    assert proxy['Config']['Labels'].get('io.graphato.e2e.owner')
                    assert proxy['HostConfig']['Memory']==128*1024**2
                    proxies[identity]={'image':proxy['Image'],'first_seen':time.time()}
                logs=subprocess.run(['docker','logs','--since',str(int(started)), '--tail','200',identity],capture_output=True,text=True,timeout=8)
                # Never save the original log: Caddy request objects may contain
                # credentials, account names or query parameters.
                for line in (logs.stdout+'\n'+logs.stderr).splitlines():
                    try:
                        row=json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(row,dict) or row.get('status')!=502:
                        continue
                    request=row.get('request') or {}
                    route=str(request.get('uri','')).split('?',1)[0]
                    if route not in {'/api/v1/commands','/api/v1/events','/api/v1/auth/login','/api/v1/info','/api/v1/health'}:
                        route='other-api'
                    safe={'ts':row.get('ts'),'status':502,'duration':row.get('duration'),
                          'method':request.get('method'),'route':route,
                          'proxy_id':identity}
                    key=json.dumps(safe,sort_keys=True)
                    if key not in proxy_seen:
                        proxy_seen.add(key)
                        proxy_rows.append(safe)
                        with (work/'proxy-errors.jsonl').open('a') as stream:
                            stream.write(json.dumps(safe)+'\n')
        for identity in ids:
            try:
                server = json.loads(call(['inspect', identity]))[0]
            except subprocess.CalledProcessError:
                event('fixture-cleanup-race', service='server')
                continue
            assert server['Image'] == runtime
            assert server['Config']['Labels'].get('io.graphato.e2e.owner')
            if not server['State']['Running'] or server['State']['Pid']<=1:
                # The original test deliberately restarts this container. A
                # ps/inspect race is an expected transition, not loss of ownership.
                continue
            try:
                namespace=pathlib.Path('/proc',str(server['State']['Pid']),'ns/net').stat().st_ino
            except FileNotFoundError:
                continue
            generation=(identity,namespace)
            if generation in seen:
                continue
            seen.add(generation)
            output = work / ('server-' + str(len(seen)))
            output.mkdir(mode=0o700)
            name = 'leroy-http-' + work.name + '-' + str(len(seen))
            observer = call(['run', '-d', '--name', name, '--label', owner,
                '--network', 'none', '--pid', 'host', '--read-only', '--user', '0:0',
                '--cap-drop', 'ALL', '--cap-add', 'SYS_ADMIN', '--cap-add', 'NET_RAW',
                '--cap-add', 'SYS_PTRACE', '--cap-add', 'DAC_OVERRIDE',
                '--cap-add', 'NET_ADMIN',
                '--security-opt', 'apparmor=graphato-server', '--security-opt', 'no-new-privileges:true',
                '--memory', '128m', '--memory-swap', '128m', '--cpus', '0.25', '--pids-limit', '32',
                '--log-opt', 'mode=non-blocking', '--log-opt', 'max-buffer-size=1m',
                '--mount', 'type=bind,src='+str(work/'observe.py')+',dst=/observe.py,readonly',
                '--mount', 'type=bind,src='+str(key)+',dst=/identity-key,readonly',
                '--mount', 'type=bind,src='+str(output)+',dst=/metadata',
                '--entrypoint', 'python3', runtime, '-B', '/observe.py', '--pseudonymous-clients', '--identity-key-file','/identity-key',
                '--packet-buffer-bytes','8388608',
                '--output', '/metadata/http-metadata.jsonl', '--network-namespace-pid', str(server['State']['Pid'])], timeout=30)
            observers.append(observer)
            event('observer-dispatched', server_id=identity, server_pid=server['State']['Pid'], network_namespace_inode=namespace, server_started_at=server['State']['StartedAt'], observer_id=observer,
                  compose_project=server['Config']['Labels']['com.docker.compose.project'])
        time.sleep(0.5)
except Exception as error:
    event('watch-error', error_type=type(error).__name__)
finally:
    retained = []
    for identity in observers:
        info = json.loads(call(['inspect', identity]))[0]
        assert info['Config']['Labels'].get('io.leroy.group-observer') == work.name
        if info['State']['Running']:
            call(['kill', '--signal', 'TERM', identity])
        deadline = time.monotonic()+20
        while time.monotonic()<deadline:
            info = json.loads(call(['inspect', identity]))[0]
            if not info['State']['Running']:
                break
            time.sleep(0.5)
        if info['State']['Running']:
            event('observer-cleanup-incomplete', observer_id=identity)
            continue
        logs=subprocess.run(['docker','logs','--tail','30',identity],capture_output=True,text=True,timeout=8)
        text=logs.stdout+'\n'+logs.stderr
        retained.append({'id': identity, 'exit_code': info['State']['ExitCode'],
                         'oom_killed': info['State']['OOMKilled'],
                         'diagnostic_flags':{key:text.count(key) for key in ('PermissionError','Operation not permitted','Cannot join inspected fixture network','FileNotFoundError','AssertionError','Passive metadata observer ready')}})
        call(['rm', identity])
    metadata = []
    for path in sorted(work.glob('server-*/http-metadata.jsonl')):
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        metadata.append({'path':path.relative_to(work).as_posix(),'rows':len(rows),
                         'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                         'first':rows[0] if rows else None,'last':rows[-1] if rows else None})
    result={'started_at':started,'finished_at':time.time(),'observers':retained,'metadata':metadata,
            'proxies':proxies,'proxy_502_records':len(proxy_rows),'encrypted_browser_http_observed':False,
            'events':events,'raw_packets_persisted':False,'credentials_persisted':False,
            'browser_dom_observed':False,'observer_overhead_excluded':False,
            'application_sources_and_tests_changed':False,'full_release_acceptance':False}
    (work/'finished.json').write_text(json.dumps(result,indent=2)+'\n')
