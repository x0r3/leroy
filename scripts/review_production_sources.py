"""Read production Jenkins source identities without exposing scripts or credentials."""

import json
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script

PROGRAM = r'''
import hashlib,json,pathlib,re,subprocess,xml.etree.ElementTree as ET
from urllib.parse import urlsplit,urlunsplit
info=json.loads(subprocess.check_output(['docker','inspect','jenkins'],text=True,timeout=20))[0]
home=pathlib.Path(next(m['Source'] for m in info['Mounts'] if m['Destination']=='/var/jenkins_home')).resolve(strict=True)
jobs=(home/'jobs').resolve(strict=True);assert jobs.is_relative_to(home)
pending=[jobs];visited=set();rows={}
def digest(data):return hashlib.sha256(data).hexdigest()
def build(root,number):
 path=root/'builds'/str(number)/'build.xml'
 assert path.resolve().is_relative_to(root.resolve())
 if not path.is_file():return {'number':number,'completed':False}
 assert path.stat().st_size<16*1024*1024
 tree=ET.parse(path).getroot()
 revisions=set();log=path.with_name('log');size=0
 if log.is_file():
  size=log.stat().st_size;assert size<512*1024*1024
  with log.open('rb') as stream:
   carry=b''
   while chunk:=stream.read(65536):
    data=carry+chunk
    revisions.update(m.decode() for m in re.findall(rb'Checking out Revision ([0-9a-f]{40})\b',data))
    carry=data[-128:]
 return {'number':number,'completed':tree.findtext('completed')=='true','result':tree.findtext('result'),
  'checkout_revisions':sorted(revisions),'log_bytes':size,'build_xml_sha256':digest(path.read_bytes())}
while pending:
 parent=pending.pop();assert parent.resolve().is_relative_to(jobs) and parent not in visited
 visited.add(parent);assert len(visited)<1000
 for root in sorted(parent.iterdir()):
  config=root/'config.xml'
  if not root.is_dir() or not config.is_file():continue
  assert root.resolve().is_relative_to(jobs)
  nested=[p for name in ['jobs','branches'] if (p:=root/name).is_dir()]
  if nested:pending.extend(nested);continue
  raw=config.read_bytes();tree=ET.fromstring(raw);name=root.relative_to(jobs).as_posix()
  definition=tree.find('definition');assert definition is not None
  urls=[]
  for entry in definition.findall('.//hudson.plugins.git.UserRemoteConfig/url'):
   value=urlsplit(entry.text);host=value.hostname or ''
   if value.port:host+=':'+str(value.port)
   urls.append(urlunsplit((value.scheme,host,value.path,'','')))
  counter=root/'nextBuildNumber';number=int(counter.read_text())-1 if counter.is_file() else 0
  current=build(root,number) if number else None
  completed=current if current and current['completed'] else None
  for previous in range(number-1,max(0,number-50),-1):
   if completed:break
   candidate=build(root,previous)
   if candidate['completed']:completed=candidate
  inline=definition.findtext('script')
  rows[name]={'configuration_sha256':digest(raw),'definition_class':definition.get('class'),
   'script_path':definition.findtext('scriptPath'),'inline_script_sha256':digest(inline.replace('\r\n','\n').encode()) if inline is not None else None,
   'source_urls':urls,'branches':[node.text for node in definition.findall('.//hudson.plugins.git.BranchSpec/name')],
   'parameter_names':[node.text for node in tree.findall('.//parameterDefinitions/*/name')],
   'latest_build':current,'latest_completed_build':completed}
assert len(rows)==13
print(json.dumps({'read_only':True,'jobs':rows}))
'''


def main():
    folder = ROOT / "test-results/nas-parity/followup/production-source-review"
    folder.mkdir(exist_ok=True)
    at = datetime.now(timezone.utc)
    result = run_script("python3 - <<'PY'\n" + PROGRAM + "\nPY\n",
                        ROOT / ".local/nas-ssh.json", sudo=True, timeout=90)
    assert result.returncode == 0, "Read-only production inventory failed; credentials remain private"
    record = json.loads(result.stdout)
    record["observed_at"] = at.isoformat()
    destination = folder / ("inventory-" + at.strftime("%Y%m%dT%H%M%SZ") + ".json")
    assert not destination.exists()
    destination.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"evidence": destination.relative_to(ROOT).as_posix(),
                      "jobs": {name: item["latest_completed_build"] for name, item in record["jobs"].items()}}))


if __name__ == "__main__":
    main()
