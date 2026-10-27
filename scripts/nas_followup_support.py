"""Bounded helpers for the owned comparison Docker daemon and test Jenkins."""

import json
import threading
import time

from compare_nas_antares import jenkins_python
from nas_ssh import ROOT, run_script
from nas_verified_container import discover_program, verify_program

_PRODUCTION_PIN = None
_PRODUCTION_PIN_LOCK = threading.Lock()


def production_prelude():
    """Bind the read-only production data mount before adding VM load."""
    global _PRODUCTION_PIN
    with _PRODUCTION_PIN_LOCK:
        if _PRODUCTION_PIN is None:
            program = discover_program('jenkins', mounts=('/var/jenkins_home',))
            response = run_script("python3 - <<'PY'\n" + program + '\nPY\n',
                                  ROOT / '.local/nas-ssh.json', sudo=True, timeout=45)
            if response.returncode:
                raise RuntimeError(response.stderr[-1500:])
            _PRODUCTION_PIN = json.loads(response.stdout)
    return verify_program(_PRODUCTION_PIN) + "\nhome=pathlib.Path(PIN['mounts']['/var/jenkins_home']['source'])\n"


def remote(program, timeout=120):
    result = run_script(
        "python3 - <<'PY'\n" + program + "\nPY\n", ROOT / ".local/nas-ssh.json", timeout=timeout
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    return result.stdout


def inner(*args, timeout=120):
    program = "import pathlib,subprocess,sys\nassert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()\nresult=subprocess.run(['docker','exec','leroy-nas-parity-docker-1','docker',*ARGS],text=True,capture_output=True,timeout=LIMIT)\nif result.returncode:\n sys.stderr.write(result.stderr[-1500:]);sys.exit(result.returncode)\nprint(result.stdout)\n"
    return remote("ARGS=" + repr(list(args)) + "\nLIMIT=" + repr(timeout - 15) + "\n" + program, timeout)


def jenkins_api(path, body=None, content_type=None):
    program = r"""
import base64,http.cookiejar,json,os,urllib.request
headers={'Authorization':'Basic '+base64.b64encode(('admin:'+os.environ['PARITY_PASSWORD']).encode()).decode()}
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def request(path,data=None):
 with opener.open(urllib.request.Request('http://127.0.0.1:8080'+path,headers=headers,data=data),timeout=30) as response:
  return response.read(),dict(response.headers)
if BODY is not None:
 crumb=json.loads(request('/crumbIssuer/api/json')[0]);headers[crumb['crumbRequestField']]=crumb['crumb']
 if CONTENT_TYPE:headers['Content-Type']=CONTENT_TYPE
payload,response_headers=request(PATH,None if BODY is None else BODY.encode())
print(json.dumps({'text':payload.decode(errors='replace'),'headers':response_headers}))
"""
    data = "PATH=" + repr(path) + "\nBODY=" + repr(body) + "\nCONTENT_TYPE=" + repr(content_type) + "\n"
    return json.loads(jenkins_python(data + program, timeout=75))


def start_jenkins():
    inner("start", "jenkins-parity")
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        try:
            return jenkins_api("/api/json?tree=mode")
        except (RuntimeError, json.JSONDecodeError):
            time.sleep(5)
    raise TimeoutError("Owned comparison Jenkins did not become ready")


def production_build():
    """Read the existing production build record without loading its Java API."""
    program = r"""
import json,pathlib,subprocess,xml.etree.ElementTree as ET
root=(home/'jobs/graphato-ci').resolve(strict=True)
assert root.is_relative_to(home)
number=int((root/'nextBuildNumber').read_text())-1
assert number>0
record=(root/'builds'/str(number)/'build.xml')
assert record.resolve().is_relative_to(root)
state={'number':number,'building':True,'result':None}
if record.is_file():
 assert record.stat().st_size<16*1024*1024
 try:
  tree=ET.parse(record).getroot()
  state.update(building=tree.findtext('completed')!='true',result=tree.findtext('result'),timestamp=tree.findtext('startTime'))
 except ET.ParseError:pass
verify_pin(PIN)
print(json.dumps(state))
"""
    response = run_script(
        "python3 - <<'PY'\n" + production_prelude() + program + "\nPY\n", ROOT / ".local/nas-ssh.json",
        sudo=True, timeout=45,
    )
    if response.returncode:
        raise RuntimeError(response.stderr[-1500:])
    return json.loads(response.stdout)


def wait_production_build():
    """Read-only: leave production builds alone and avoid adding another compiler."""
    previous = None
    deadline = time.monotonic() + 14400
    while time.monotonic() < deadline:
        state = production_build()
        if state != previous:
            print("Production Graphato build (read-only):", json.dumps(state), flush=True)
            previous = state
        if not state["building"]:
            return state
        time.sleep(45)
    raise TimeoutError("Production compilation still active; no competing test compiler started")


def production_jobs_program(*, history=True):
    """The same pinned read for Windows SSH and NAS-local admission."""
    assert type(history) is bool
    program = r"""
import json,pathlib,subprocess,xml.etree.ElementTree as ET
jobs=(home/'jobs').resolve(strict=True);assert jobs.is_relative_to(home)
rows={};pending=[jobs];visited=set();job_roots={}
while pending:
 parent=pending.pop();assert parent.resolve().is_relative_to(jobs) and parent not in visited
 visited.add(parent);assert len(visited)<=1000
 for root in sorted(parent.iterdir()):
  if not root.is_dir() or not (root/'config.xml').is_file():continue
  assert root.resolve().is_relative_to(jobs)
  nested=[p for name in ['jobs','branches'] if (p:=root/name).is_dir()]
  if nested:pending.extend(nested);continue
  name=root.relative_to(jobs).as_posix();next_number=root/'nextBuildNumber'
  assert next_number.resolve().is_relative_to(root.resolve())
  if not next_number.is_file() and (root/'builds').is_dir():
   assert not any(p.name.isdecimal() for p in (root/'builds').iterdir()),'Build history exists without its counter'
  number=int(next_number.read_text())-1 if next_number.is_file() else 0
  assert number>=0 and len(rows)<1000
  state={'number':number,'building':number>0,'result':None}
  record=root/'builds'/str(number)/'build.xml'
  assert record.resolve().is_relative_to(root.resolve())
  if number and record.is_file():
   assert record.stat().st_size<16*1024*1024
   try:
    tree=ET.parse(record).getroot()
    assert tree.tag=='flow-build','Unrecognized build record; no quiet-production claim'
    state.update(building=tree.findtext('completed')!='true',result=tree.findtext('result'))
   except ET.ParseError:pass
  rows[name]=state
  job_roots[name]=root
assert rows
active=[{'job':name,'number':row['number']} for name,row in rows.items() if row['building']]
# A completed latest build does not prove an older concurrent build completed.
# Scan history only when the inexpensive latest-record check could report idle.
history_verified=False
if not active and VERIFY_HISTORY:
 count=0;total=0
 for name,root in job_roots.items():
  builds=root/'builds'
  if not builds.is_dir():continue
  for entry in builds.iterdir():
   if not entry.name.isdecimal() or not entry.is_dir():continue
   assert entry.resolve().is_relative_to(root.resolve())
   number=int(entry.name);path=entry/'build.xml';count+=1;assert count<=10000
   if not path.is_file():
    active.append({'job':name,'number':number,'record_missing':True});continue
   assert path.resolve().is_relative_to(root.resolve())
   size=path.stat().st_size;assert size<16*1024**2;total+=size;assert total<64*1024**2
   try:
    tree=ET.parse(path).getroot();assert tree.tag=='flow-build'
    if tree.findtext('completed')!='true':active.append({'job':name,'number':number})
   except ET.ParseError:active.append({'job':name,'number':number,'record_incomplete':True})
 history_verified=True
verify_pin(PIN)
print(json.dumps({'read_only':True,'jobs':rows,'active_builds':active,
 'older_concurrent_build_history_verified':history_verified,'live_queue_state_verified':False}))
"""
    return 'VERIFY_HISTORY=' + repr(history) + '\n' + production_prelude() + program


def production_jobs(*, history=True, timeout=45):
    """Read current production job records, including unbuilt and nested jobs."""
    assert type(timeout) in (int, float) and 0 < timeout <= 45
    response = run_script(
        "python3 - <<'PY'\n" + production_jobs_program(history=history) + "\nPY\n", ROOT / ".local/nas-ssh.json",
        sudo=True, timeout=timeout,
    )
    if response.returncode:
        from nas_release_vm import SSHTransportUnavailable, ssh_transport_unavailable

        if ssh_transport_unavailable(response):
            raise SSHTransportUnavailable('NAS production observation unavailable; current state is unknown')
        raise RuntimeError(response.stderr[-1500:])
    return json.loads(response.stdout)


def wait_production_jobs():
    """Leave production untouched and wait for all recorded jobs to be idle."""
    previous = None
    deadline = time.monotonic() + 14400
    while time.monotonic() < deadline:
        state = production_jobs()
        active = state.get('active_builds',
                           [{'job': name, 'number': row['number']} for name, row in state['jobs'].items() if row['building']])
        if active != previous:
            print("Active production Jenkins jobs (read-only):", json.dumps(active), flush=True)
            previous = active
        if not active:
            return state
        time.sleep(45)
    raise TimeoutError("Production jobs still active; no diagnostic started")
