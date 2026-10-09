"""Read one bounded build/pressure snapshot without querying a busy Docker API."""

import argparse
import json
import subprocess
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script
from stage_nas_production_graphato import COMMIT

PROGRAM = r'''
import json,os,pathlib,re,time,xml.etree.ElementTree as ET
from datetime import datetime
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
configs=list(pathlib.Path('/volume1/@docker/containers').glob('7d029*/config.v2.json'))
assert len(configs)==1
config=json.loads(configs[0].read_text())
assert config['Name']=='/leroy-nas-parity-docker-1' and config['ID'].startswith('7d029')
group=pathlib.Path('/sys/fs/cgroup/system.slice','docker-'+config['ID']+'.scope')
row={'at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'read_only':True,'root_id':config['ID']}
for key in ('memory.current','memory.max','memory.swap.current','memory.swap.max'):
 row[key]=(group/key).read_text().strip()
row['memory.events']=dict(line.split() for line in (group/'memory.events').read_text().splitlines())
row['memory.pressure']=(group/'memory.pressure').read_text().splitlines()
row['io.pressure']=(group/'io.pressure').read_text().splitlines()
row['host_available_kib']=int(next(line.split()[1] for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))
row['host_memory_kib']={line.split(':',1)[0]:int(line.split()[1]) for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.split(':',1)[0] in {'MemTotal','MemAvailable','SwapTotal','SwapFree','Dirty','Writeback'}}
if LEROY_RUN:
 controller=[]
 for metadata in pathlib.Path('/volume1/@docker/containers').glob('*/config.v2.json'):
  try:
   item=json.loads(metadata.read_text())
   if item['Name']=='/leroy-nas-parity-controller-1':controller.append(item)
  except FileNotFoundError:pass
 assert len(controller)==1
 item=controller[0]
 log=pathlib.Path(item['LogPath']);assert log.parent==pathlib.Path('/volume1/@docker/containers')/item['ID']
 heartbeats=[]
 with log.open('rb') as stream:
  start=max(0,log.stat().st_size-1024**2);stream.seek(start)
  if start:stream.readline()
  lines=stream.read(1024**2).splitlines()
 for line in lines:
  try:entry=json.loads(line)
  except ValueError:continue
  match=re.search(r'POST /internal/runs/'+LEROY_RUN+r'/heartbeat HTTP/1.1" (\d{3})',entry['log'])
  if match:heartbeats.append({'at':entry['time'],'http_status':int(match[1])})
 if heartbeats:
  stamps=[datetime.fromisoformat(value['at'].replace('Z','+00:00')).timestamp() for value in heartbeats]
  row['sampled_heartbeats']={'count':len(heartbeats),'first':heartbeats[0], 'last':heartbeats[-1],
    'largest_observed_gap_seconds':max((b-a for a,b in zip(stamps,stamps[1:])),default=0),
    'last_observed_age_seconds':round(time.time()-stamps[-1],3),
    'all_http_success':all(value['http_status']==200 for value in heartbeats),'bounded_log_sample_bytes':1024**2}
if LEROY_RUN:
 matches=[]
 for path in pathlib.Path('/volume1/@docker/volumes/leroy-nas-parity_engine/_data/containers').glob('*/config.v2.json'):
  try:
   item=json.loads(path.read_text())
   if item['Name']=='/leroy-'+LEROY_RUN:matches.append(item)
  except FileNotFoundError:pass
 assert len(matches)<=1
 row['job_control']={'run':LEROY_RUN,'container_present':bool(matches)}
 if matches:
  item=matches[0]
  logfile=pathlib.PurePosixPath(item['LogPath']);base=pathlib.PurePosixPath('/var/lib/docker/containers')/item['ID']
  assert logfile.parent==base
  host_log=pathlib.Path('/volume1/@docker/volumes/leroy-nas-parity_engine/_data')/logfile.relative_to('/var/lib/docker')
  diagnostics=[]
  if host_log.is_file():
   with host_log.open('rb') as stream:
    start=max(0,host_log.stat().st_size-65536);stream.seek(start)
    if start:stream.readline()
    lines=stream.read(65536).splitlines()
   for line in lines:
    try:entry=json.loads(line)
    except ValueError:continue
    if entry['log'].startswith('Leroy lease '):
     safe=re.fullmatch(r'Leroy lease renewal failed: (HTTP \d{3}|[A-Za-z]+)(; seconds since confirmation: [\d.]+)?\n?',entry['log'])
     if safe:diagnostics.append({'at':entry['time'],'diagnostic':safe[0].strip()})
     else:diagnostics.append({'at':entry['time'],'diagnostic':'Unparsed lease diagnostic; no outcome inferred'})
  row['job_control']['lease_diagnostics']=diagnostics
  row['job_control']['lease_diagnostic_parser_version']=2
  controls=[p for p in group.rglob('memory.max') if item['ID'] in p.as_posix()]
  assert len(controls)<=1
  row['job_control'].update(container_id=item['ID'],runtime_cgroup_available=bool(controls))
  if controls:
   leaf=controls[0].parent
   row['job_control'].update(**{key:(leaf/key).read_text().strip() for key in ['memory.current','memory.max','memory.low','memory.swap.current','memory.swap.max','memory.pressure','io.pressure','cpu.pressure']})
  processes=[]
  for path in pathlib.Path('/proc').glob('[0-9]*'):
   try:
    if item['ID'] not in (path/'cgroup').read_text():continue
    args=(path/'cmdline').read_bytes().split(b'\0')
    if b'leroy.worker' not in args:continue
    status=dict(line.split(':',1) for line in (path/'status').read_text().splitlines())
    processes.append({'pid':int(path.name),'rss_kib':int(status.get('VmRSS','0 kB').split()[0]),'swap_kib':int(status.get('VmSwap','0 kB').split()[0]),'thread_waits':{p.name:(p/'wchan').read_text() for p in (path/'task').iterdir()}})
   except (FileNotFoundError,PermissionError,ProcessLookupError):pass
  row['job_control']['worker_processes']=processes
if PROCESSES:
 processes=[]
 for path in pathlib.Path('/proc').glob('[0-9]*'):
  try:
   if config['ID'] not in (path/'cgroup').read_text():continue
   status=dict(line.split(':',1) for line in (path/'status').read_text().splitlines())
   rss=int(status.get('VmRSS','0 kB').split()[0]);swap=int(status.get('VmSwap','0 kB').split()[0])
   if rss+swap<50000:continue
   fields=(path/'stat').read_text().split(') ',1)[1].split()
   cpu=(int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK')
   processes.append({'pid':int(path.name),'name':status['Name'].strip(),'state':status['State'].strip(),'rss_kib':rss,'swap_kib':swap,'wchan':(path/'wchan').read_text(),'cpu_seconds':cpu,'threads':int(status.get('Threads','0'))})
   if status['Name'].strip()=='rustc':
    processes[-1]['io']=(path/'io').read_text().splitlines()
    processes[-1]['thread_waits']={p.name:(p/'wchan').read_text() for p in (path/'task').iterdir()}
    relative=(path/'cgroup').read_text().strip().split('::',1)[1]
    leaf=pathlib.Path('/sys/fs/cgroup',relative.lstrip('/'))
    assert leaf.resolve().is_relative_to(group.resolve())
    limits=[]
    while leaf!=group:
     limits.append({'path':leaf.relative_to(group).as_posix(),**{key:(leaf/key).read_text().strip() for key in ('memory.max','memory.current','memory.high','memory.swap.max','memory.swap.current','cpu.max')},'memory.events':(leaf/'memory.events').read_text().splitlines()})
     leaf=leaf.parent
    processes[-1]['descendant_limits']=limits
  except (FileNotFoundError,PermissionError,ProcessLookupError):pass
 row['owned_large_processes']=sorted(processes,key=lambda p:p['rss_kib']+p['swap_kib'],reverse=True)[:16]
home=pathlib.Path('/volume1/@docker/volumes/leroy-nas-parity_engine/_data/volumes/jenkins-parity-aligned-home/_data')
row['builds']={}
for job,number in BUILDS.items():
 path=home/'jobs'/job/'builds'/str(number)
 state={'number':number,'started':(path/'build.xml').exists()}
 if state['started']:
  try:
   xml=ET.parse(path/'build.xml').getroot()
   state.update(building=xml.findtext('completed')!='true',result=xml.findtext('result'))
  except ET.ParseError:state['building']=True
 if (path/'log').is_file():
  with (path/'log').open('rb') as stream:
   stream.seek(max(0,(path/'log').stat().st_size-8192));tail=stream.read().decode(errors='replace')
  state['console_tail']=tail
  stages=re.findall(r'\[Pipeline\] \{ \(([^)]+)\)',tail)
  state['last_visible_stage']=stages[-1] if stages else None
  checks=re.findall(r'Post-deployment (?:web|quality): ([a-z][a-z0-9-]*)',tail)
  state['last_visible_check_group']=checks[-1] if checks else None
  state['recent_started_check_groups']=list(dict.fromkeys(checks[-6:]))
 row['builds'][job]=state
print(json.dumps(row))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processes", action="store_true")
    parser.add_argument("--existing-host", action="store_true", help="Observe the separately recorded prepared-host jobs")
    args = parser.parse_args()
    folder = ROOT / "test-results/nas-parity/followup/candidates/graphato" / COMMIT
    if args.existing_host:
        folder = folder / "scenarios/root-private-existing-host"
        assert (folder / "scenario.json").is_file()
    builds = json.loads((folder / "jenkins-release-numbers.json").read_text())
    root_pipeline = "graphato-release-acceptance" if args.existing_host else "graphato-ci"
    pair_path = folder / root_pipeline / "pair.json"
    leroy_run = json.loads(pair_path.read_text()).get("leroy_run") if pair_path.exists() else None
    assert set(builds) <= {"graphato-ci", "graphato-release-acceptance", "graphato-postdeploy-web", "graphato-postdeploy-quality"}
    try:
        result = run_script("python3 - <<'PY'\nBUILDS=" + repr(builds) + "\nPROCESSES=" + repr(args.processes) + "\nLEROY_RUN=" + repr(leroy_run) + "\n" + PROGRAM + "\nPY\n",
                            ROOT / ".local/nas-ssh.json", sudo=True, timeout=45)
        if result.returncode:
            raise RuntimeError(result.stderr[-1000:])
        row = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        row = {"at": datetime.now(timezone.utc).isoformat(), "read_only": True, "ssh_observation_timed_out": True}
    with (folder / "nas-pressure-observations.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row) + "\n")
    display = {key: value for key, value in row.items() if key != "builds"}
    display["builds"] = {name: {key: value for key, value in state.items() if key != "console_tail"}
                         for name, state in row.get("builds", {}).items()}
    print(json.dumps(display))


if __name__ == "__main__":
    main()
