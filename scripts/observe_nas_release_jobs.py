"""Read bounded, secret-free diagnostics from owned release workers only."""

import argparse
import inspect
import json
import subprocess
import time
from datetime import datetime, timezone

import nas_release_vm as vm
from nas_ssh import ROOT


def safe_transport(value):
    """Accept only the fixed numeric diagnostic schema; reject unexpected data."""
    import math

    def number(v):
        return type(v) in (int, float) and math.isfinite(v) and 0 <= v < 10**12

    if not isinstance(value, dict) or not number(value.get('at_epoch')):
        return None
    if value.get('event') == 'thread':
        keys = {'event', 'at_epoch', 'pid', 'thread_id', 'controller_file_mapping_present', 'proxy_environment_present'}
        valid = (set(value) == keys and all(type(value[k]) is int and 0 < value[k] < 2**32 for k in ('pid', 'thread_id'))
                 and (value['controller_file_mapping_present'] is None or type(value['controller_file_mapping_present']) is bool)
                 and type(value['proxy_environment_present']) is bool)
    elif value.get('event') == 'request':
        keys = {'event', 'at_epoch', 'wall_seconds', 'thread_cpu_seconds', 'thread_usage_delta',
                'last_event', 'phases_seconds', 'request_failed'}
        phases = {'connect', 'connect_unix', 'tls', 'send_headers', 'send_body', 'receive_headers', 'receive_body', 'close'}
        events = {p + '.' + stage for p in phases for stage in ('started', 'complete', 'failed')}
        delta = value.get('thread_usage_delta')
        durations = value.get('phases_seconds')
        valid = (set(value) == keys and all(number(value[k]) for k in ('wall_seconds', 'thread_cpu_seconds'))
                 and (value['last_event'] is None or type(value['last_event']) is str and value['last_event'] in events)
                 and type(value['request_failed']) is bool and isinstance(durations, dict)
                 and set(durations) <= phases and all(number(v) for v in durations.values())
                 and (delta is None or isinstance(delta, dict) and set(delta) == {'majflt', 'minflt', 'inblock', 'nvcsw', 'nivcsw'}
                      and all(type(v) is int and 0 <= v < 10**12 for v in delta.values())))
    else:
        valid = False
    return value if valid else None


PROGRAM = r'''
import json,pathlib,re,subprocess
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
outer=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-docker-1'],text=True,timeout=15))[0]
assert outer['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
prefix=['docker','exec',outer['Id'],'docker']
names=subprocess.check_output(prefix+['ps','-a','--filter','label=io.leroy.runner=runner-nas-parity','--format','{{.Names}}'],text=True,timeout=15).split()
rows=[]
for name in names:
 assert re.fullmatch(r'leroy-[0-9a-f]{32}',name)
 item=json.loads(subprocess.check_output(prefix+['inspect',name],text=True,timeout=15))[0]
 assert item['Config']['Labels']['io.leroy.runner']=='runner-nas-parity'
 result=subprocess.run(prefix+['logs','--timestamps','--tail','100','--since','120s',name],capture_output=True,text=True,timeout=15)
 # Never save arbitrary job output, exception text or environment values.
 events=[];timings=[];transports=[]
 for line in (result.stdout+'\n'+result.stderr).splitlines():
  match=re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.[0-9]{1,9})?Z) '
   r'(Leroy lease (?:renewal failed: (?:[A-Za-z]+|HTTP [0-9]{3})(?:; seconds since confirmation: [0-9.]+)?|stopped: Controller lease could not be renewed(?: \(last failure: (?:[A-Za-z]+|HTTP [0-9]{3})\))?))',line)
  if match:events.append({'at':match[1],'message':match[2]})
  timing=re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.[0-9]{1,9})?Z) Leroy lease timing: (\{.{1,500}\})',line)
  if timing:
   try:
    value=json.loads(timing[2]);event=value.pop('event',None)
    fields={'slow_confirmation':{'request_seconds','previous_confirmation_age_seconds'},
     'local_deadline':{'unconfirmed_seconds','last_request_seconds','loop_gap_seconds'}}
    if event in fields and set(value)==fields[event] and all(v is None or type(v) in (int,float) and 0<=v<10**9 for v in value.values()):
     timings.append({'at':timing[1],'event':event,**value})
   except (ValueError,TypeError):pass
  transport=re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.[0-9]{1,9})?Z) Leroy lease transport: (\{.{1,2000}\})',line)
  if transport:
   try:
    value=safe_transport(json.loads(transport[2]))
    if value is not None:transports.append({'at':transport[1],**value})
   except (ValueError,TypeError,KeyError):pass
 rows.append({'name':name,'image':item['Image'],'state':{key:item['State'][key] for key in ('Running','OOMKilled','ExitCode')},
  'lease_diagnostics':[e['message'] for e in events],'lease_diagnostics_with_timestamps':events,
  'lease_timing_diagnostics':timings,
  'lease_transport_diagnostics':transports,
  'log_read_succeeded':result.returncode==0})
print(json.dumps({'owned_jobs':rows,'arbitrary_logs_retained':False,'production_modified':False}))
'''
PROGRAM = inspect.getsource(safe_transport) + '\n' + PROGRAM


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', required=True)
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    folder = (ROOT / args.folder).resolve()
    assert folder.is_relative_to(ROOT / 'test-results/nas-parity/followup')
    assert (folder / 'prepared.json').is_file()
    deadline = time.monotonic() + 9 * 3600
    previous = None
    while time.monotonic() < deadline:
        value = {'at': datetime.now(timezone.utc).isoformat()}
        try:
            value.update(json.loads(vm.remote(PROGRAM, timeout=60)))
        except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
            value['observation_error'] = type(error).__name__
        with (folder / 'owned-job-diagnostics.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(value) + '\n')
        state = {key: item for key, item in value.items() if key != 'at'}
        if state != previous:
            print(json.dumps(value), flush=True)
            previous = state
        if not args.watch or (folder / 'final-state.json').is_file():
            break
        time.sleep(20)


if __name__ == '__main__':
    main()
