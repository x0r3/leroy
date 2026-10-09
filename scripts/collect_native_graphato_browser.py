"""Read bounded, completed native Jenkins browser archives without starting jobs."""

import argparse
import base64
import hashlib
import json
import re
import tarfile
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script

PROGRAM = r'''
import base64,hashlib,json,pathlib,re,subprocess,xml.etree.ElementTree as ET
info=json.loads(subprocess.check_output(['docker','inspect','jenkins'],text=True,timeout=20))[0]
home=pathlib.Path(next(m['Source'] for m in info['Mounts'] if m['Destination']=='/var/jenkins_home')).resolve(strict=True)
build=(home/'jobs/graphato-postdeploy-web/builds'/str(NUMBER)).resolve(strict=True)
assert build.is_relative_to(home)
record=build/'build.xml';assert record.stat().st_size<16*1024**2
tree=ET.parse(record).getroot();assert tree.findtext('completed')=='true'
result=tree.findtext('result');assert result in {'SUCCESS','FAILURE','UNSTABLE'}
archive=build/'archive/target/postdeploy-web';files=[]
for name in ('result.json','artifacts.tar.gz'):
 path=archive/name;assert not path.is_symlink() and path.resolve(strict=True).is_relative_to(build)
 assert path.stat().st_size<=2*1024**2
 data=path.read_bytes()
 if name=='result.json':
  receipt=json.loads(data);assert re.fullmatch('[a-f0-9]{40}',receipt['commit'])
  assert receipt['suite']=='web' and receipt['requestedGroup']=='all'
 files.append({'name':name,'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),
               'content':base64.b64encode(data).decode()})
print(json.dumps({'job':'graphato-postdeploy-web','number':NUMBER,'result':result,'read_only':True,
 'production_modified':False,'production_jobs_started':False,'files':files}))
'''


def collect(number):
    folder = ROOT / 'test-results/nas-parity/followup/native-browser-observations' / ('web-' + str(number))
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / 'observation.json'
    assert not destination.exists(), 'Retain the first archived observation'
    response = run_script("python3 - <<'PY'\nNUMBER=" + repr(number) + '\n' + PROGRAM + '\nPY\n',
                          ROOT / '.local/nas-ssh.json', sudo=True, timeout=45)
    assert response.returncode == 0, 'Read-only native browser collection failed'
    value = json.loads(response.stdout)
    for item in value['files']:
        data = base64.b64decode(item.pop('content'), validate=True)
        assert len(data) == item['size'] and hashlib.sha256(data).hexdigest() == item['sha256']
        (folder / item['name']).write_bytes(data)
    receipt = json.loads((folder / 'result.json').read_text())
    value['commit'] = receipt['commit']
    value['checks'] = {name: row['passed'] for name, row in receipt['checks'].items()}
    value['soak_files'] = {}
    with tarfile.open(folder / 'artifacts.tar.gz') as archive:
        members = archive.getmembers()
        assert len(members) <= 2000 and sum(member.size for member in members) <= 64 * 1024**2
        for member in members:
            if not (member.name.startswith('browser-soak/') or member.name == 'browser-soak.log'):
                continue
            assert member.isfile() and member.size < 16 * 1024**2
            data = archive.extractfile(member).read()
            value['soak_files'][member.name] = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            if member.name == 'browser-soak.log':
                rows = []
                for line in data.decode(errors='replace').splitlines():
                    try:
                        row = json.loads(line[line.index('{'):])
                    except (ValueError, TypeError):
                        continue
                    if isinstance(row, dict) and row.get('event') == 'boundedSoak':
                        rows.append(row)
                value['bounded_soak_metrics'] = rows
            elif member.name == 'browser-soak/open/results.json':
                cases = json.loads(data)
                value['soak_case_outcomes'] = [
                    {'id': case['id'], 'passed': case['passed'], 'duration_ms': case.get('durationMs'),
                     'prompt_rate_limit_failure': 'serverRateLimited' in case.get('error', ''),
                     'send_session_prompt_failure': 'sendSessionPrompt' in case.get('error', ''),
                     'error_sha256': hashlib.sha256(case.get('error', '').encode()).hexdigest()}
                    for case in cases]
    value['at'] = datetime.now(timezone.utc).isoformat()
    destination.write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({key: value.get(key) for key in
                      ('number', 'result', 'commit', 'checks', 'bounded_soak_metrics', 'soak_case_outcomes')}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='append', type=int, required=True)
    args = parser.parse_args()
    assert len(args.build) <= 4 and len(set(args.build)) == len(args.build)
    assert all(re.fullmatch('[1-9][0-9]{0,5}', str(number)) for number in args.build)
    for number in args.build:
        collect(number)


if __name__ == '__main__':
    main()
