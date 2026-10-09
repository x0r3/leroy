"""Check Jenkins credential IDs and types; never export credential values."""

import json
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script

PROGRAM = r'''
import json,pathlib,re,subprocess,xml.etree.ElementTree as ET
info=json.loads(subprocess.check_output(['docker','inspect','jenkins'],text=True,timeout=20))[0]
home=pathlib.Path(next(m['Source'] for m in info['Mounts'] if m['Destination']=='/var/jenkins_home')).resolve(strict=True)
path=(home/'credentials.xml').resolve(strict=True);assert path.is_relative_to(home)
assert path.stat().st_size<=2*1024**2
tree=ET.parse(path).getroot();rows=[]
for node in tree.iter():
 identifier=node.findtext('id')
 if identifier is None:continue
 assert re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',identifier)
 rows.append({'id':identifier,'type':node.tag,'scope':node.findtext('scope')})
assert len(rows)<1000
selectors={}
for item in info['Config']['Env']:
 name,_,value=item.partition('=')
 if name.endswith('_CREDENTIALS_ID') and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',value):selectors[name]=value
print(json.dumps({'read_only':True,'credential_values_exported':False,'credentials':rows,'environment_credential_selectors':selectors}))
'''


def main():
    result = run_script("python3 - <<'PY'\n" + PROGRAM + "\nPY\n",
                        ROOT / '.local/nas-ssh.json', sudo=True, timeout=90)
    assert result.returncode == 0, 'Metadata read failed; sensitive diagnostics withheld'
    record = json.loads(result.stdout)
    record.update(at=datetime.now(timezone.utc).isoformat(), production_modified=False,
                  credential_contents_or_permissions_validated=False,
                  production_replacement_ready=False,
                  scope='Presence/type only; no decryption, credential copying or production action')
    folder = ROOT / 'test-results/nas-parity/followup/cutover-preparation'
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / ('credential-metadata-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json')
    assert not destination.exists()
    destination.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'credential_ids_and_types': record['credentials'],
                      'credential_values_exported': False}), flush=True)


if __name__ == '__main__':
    main()
