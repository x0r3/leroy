"""Read native Jenkins configuration metadata without exporting secret values."""

import argparse
import json
import re
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script

PROGRAM = r'''
import hashlib,json,pathlib,re,subprocess,urllib.parse,xml.etree.ElementTree as ET
info=json.loads(subprocess.check_output(['docker','inspect','jenkins'],text=True))[0]
home=pathlib.Path(next(m['Source'] for m in info['Mounts'] if m['Destination']=='/var/jenkins_home')).resolve(strict=True)
rows=[]
safe_defaults={'TARGET_HOST','TARGET_PORT','BOOTSTRAP_USER','DEPLOY_USER','DEPLOY_DIR','DEPLOY_HOST','DEPLOY_PORT',
 'GRAPHATO_REF','GIT_URL','GIT_REF','GIT_BRANCH','GRAPHATO_HOST','GRAPHATO_PORT','REGISTRY_URL','REGISTRY_NAMESPACE',
 'IMAGE_NAME','IMAGE_TAG','TRAEFIK_HOST_RULE','PUBLIC_ORIGIN','ACME_STORAGE_PATH','PAPERLESS_API_URL','GITEA_URL',
 'GITEA_CONTAINER_NAME','GITEA_OWNER','GITEA_REPO','PHONE_HOST','PHONE_PORT','PHONE_USER','PHONE_DEST_DIR',
 'SOURCE_DIR','SOURCE_DIRS','SOURCE_PATH','LOCAL_SOURCE_DIR','SOURCE_REPOSITORY','TIMEOUT_SECONDS','DRY_RUN',
 'DOMAIN','APPLY_CHANGES'}
def safe_url(value):
 parts=urllib.parse.urlsplit(value)
 if parts.scheme and parts.netloc:
  return urllib.parse.urlunsplit((parts.scheme,parts.netloc.rsplit('@',1)[-1],parts.path,'',''))
 return value
for expected in EXPECTED:
 path=(home/'jobs'/expected/'config.xml').resolve(strict=True);assert path.is_relative_to(home)
 raw=path.read_bytes();assert len(raw)<2*1024**2
 tree=ET.fromstring(raw);definition=tree.find('definition');script=definition.findtext('script') or ''
 params=[]
 for p in tree.findall('.//parameterDefinitions/*'):
  name=p.findtext('name');record={'name':name,'kind':p.tag}
  if name in safe_defaults or name.endswith('_CREDENTIALS_ID'):
   value=p.findtext('defaultValue')
   if value is not None:record['default']=safe_url(value)
  params.append(record)
 triggers=[{'kind':t.tag,'spec':t.findtext('spec'),'ignore_post_commit_hooks':t.findtext('ignorePostCommitHooks')}
           for parent in tree.findall('.//triggers') for t in parent]
 ids=set(tree.findall('.//credentialsId'))
 selectors={t.text for t in ids if t.text}
 selectors.update(re.findall(r"credentialsId\s*[:=]\s*['\"]([^'\"]+)['\"]",script))
 rows.append({'pipeline':expected,'disabled':tree.findtext('disabled')=='true','config_sha256':hashlib.sha256(raw).hexdigest(),
  'definition_kind':definition.get('class'),'inline_script_sha256':hashlib.sha256(script.encode()).hexdigest() if script else None,
  'script_path':definition.findtext('scriptPath'),'repositories':[safe_url(t.text) for t in definition.findall('.//url') if t.text],
  'branches':[t.text for t in definition.findall('.//hudson.plugins.git.BranchSpec/name')],
  'parameters':params,'triggers':triggers,'static_credential_ids':sorted(selectors)})
print(json.dumps({'read_only':True,'production_modified':False,'secret_values_exported':False,'pipelines':rows}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observation', help='UTC timestamp for a separate read-only observation')
    args = parser.parse_args()
    if args.observation:
        assert re.fullmatch(r'\d{8}T\d{6}Z', args.observation)
    inventory = json.loads((ROOT / "src/leroy/inventory.json").read_text())
    jobs = inventory["jobs"]
    expected = [row["name"] for row in jobs]
    assert len(expected) == 13 and len(set(expected)) == 13
    result = run_script("python3 - <<'PY'\nEXPECTED=" + repr(expected) + "\n" + PROGRAM + "\nPY\n",
                        ROOT / ".local/nas-ssh.json", sudo=True, timeout=90)
    assert result.returncode == 0, result.stderr[-1000:]
    record = json.loads(result.stdout)
    originals = {row["name"]: row for row in jobs}
    for row in record["pipelines"]:
        prior = originals[row["pipeline"]]
        row["inline_script_matches_migrated_inventory"] = (
            row["inline_script_sha256"] == prior["script_sha256"] if row["inline_script_sha256"] else None)
        row["config_matches_migrated_inventory"] = row["config_sha256"] == prior["sha256"]
        row["included_in_cutover"] = row["pipeline"] != "antares-ci"
        row["leroy_pipeline_id"] = row["pipeline"]
    record.update(at=datetime.now(timezone.utc).isoformat(),
                  scope="Native Jenkins trigger/default/credential ID mapping; actual production credential contents remain in Jenkins")
    folder = ROOT / "test-results/nas-parity/followup/cutover-preparation"
    folder.mkdir(parents=True, exist_ok=True)
    filename = ('jenkins-mapping-' + args.observation + '.json') if args.observation else 'jenkins-mapping.json'
    destination = folder / filename
    assert not destination.exists(), "Preserve the recorded cutover mapping"
    destination.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"pipelines": len(record["pipelines"]), "secret_values_exported": False,
                      "inline_script_differences": [row["pipeline"] for row in record["pipelines"]
                                                    if row["inline_script_matches_migrated_inventory"] is False]}), flush=True)


if __name__ == "__main__":
    main()
