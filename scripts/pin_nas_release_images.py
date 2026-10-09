"""Pin tested images only in the idle owned stack; preserve prior configuration."""

import argparse
import json
import re
from datetime import datetime, timezone

from nas_gitea_target import idle
from nas_operations_scope import require_operations_inputs
from nas_ssh import ROOT, run_script

PROGRAM = r'''
import hashlib,json,pathlib,re,subprocess,tomllib
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
override=root/'compose.release.json';backup=root/('config/runner.toml.before-release-'+SHORT)
assert not override.exists() and not backup.exists(),'Inspect existing release pins before applying again'
prefix=['docker','exec','leroy-nas-parity-docker-1','docker']
for service,row in BEFORE['services'].items():
 info=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-'+service+'-1'],text=True))[0]
 assert info['Id']==row['container_id'] and info['Image']==row['image_id']
 assert info['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
assert not subprocess.check_output(prefix+['ps','-a','--filter','label=io.leroy.runner=runner-nas-parity','-q'],text=True).strip()
path=root/'config/runner.toml';old=path.read_bytes()
assert hashlib.sha256(old).hexdigest()==BEFORE['configuration_sha256']['config/runner.toml']
text=old.decode();profiles=tomllib.loads(text)['profiles']
for name,row in BEFORE['job_profiles'].items():
 assert profiles[name]['image']==row['image_tag']
 actual=json.loads(subprocess.check_output(prefix+['image','inspect',row['image_tag']],text=True))[0]
 assert actual['Id']==row['image_id'] and actual['RootFS']['Layers']==row['rootfs_layers']
 pattern=r'(?m)(^\[profiles\.'+re.escape(name)+r'\]\r?\n)((?:(?!^\[)[^\n]*\n)*)'
 match=re.search(pattern,text);assert match
 section,count=re.subn(r'(?m)^image\s*=\s*"[^"]+"', 'image = "'+row['image_id']+'"',match[2])
 assert count==1
 text=text[:match.start()]+match[1]+section+text[match.end():]
updated=tomllib.loads(text)['profiles']
for name,old_profile in profiles.items():
 current=updated[name]
 assert current['image']==BEFORE['job_profiles'][name]['image_id']
 assert {k:v for k,v in current.items() if k!='image'}=={k:v for k,v in old_profile.items() if k!='image'}
release={'services':{name:{'image':row['image_id']} for name,row in BEFORE['services'].items()}}
backup.write_bytes(old);backup.chmod(0o600)
override.write_text(json.dumps(release,indent=2)+'\n');override.chmod(0o600)
try:
 subprocess.run(['docker','compose','-f',str(root/'compose.yaml'),'-f',str(override),'config','-q'],check=True,capture_output=True)
 raw=subprocess.check_output(['docker','compose','-f',str(root/'compose.yaml'),'-f',str(override),'config','--format','json'])
 effective=json.loads(raw)
 assert all(effective['services'][name]['image']==row['image_id'] for name,row in BEFORE['services'].items())
 path.write_text(text);path.chmod(0o644)
 subprocess.run(['docker','restart','leroy-nas-parity-runner-1'],check=True,capture_output=True,timeout=90)
except Exception:
 path.write_bytes(old);path.chmod(0o644)
 subprocess.run(['docker','restart','leroy-nas-parity-runner-1'],capture_output=True,timeout=90)
 raise
print(json.dumps({'compose_override':str(override),'previous_runner_configuration':str(backup),
 'job_images':{name:row['image_id'] for name,row in BEFORE['job_profiles'].items()},
 'service_images':{name:row['image_id'] for name,row in BEFORE['services'].items()},
 'runner_configuration_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
 'resources_and_secret_mappings_unchanged':True,'tested_image_layers_unchanged':True,
 'effective_compose_image_pins_match_running_images':True,'runner_restarted':True,
 'production_modified':False,'secret_values_exported':False}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--infrastructure-only", action="store_true",
                        help="Pin tested CI images without claiming successful application acceptance")
    args = parser.parse_args()
    assert re.fullmatch(r"[a-f0-9]{40}", args.commit)
    folder = ROOT / "test-results/nas-parity/followup/candidates/graphato" / args.commit
    scope = require_operations_inputs(folder, args.commit, infrastructure_only=args.infrastructure_only)
    destination = folder / "release-image-pins.json"
    assert not destination.exists(), "No implicit image/config update repetition"
    before = json.loads((folder / "nas-release-configuration-before.json").read_text())
    idle()
    program = "BEFORE=" + repr(before) + "\nSHORT=" + repr(args.commit[:12]) + "\n" + PROGRAM
    result = run_script("python3 - <<'PY'\n" + program + "\nPY\n", ROOT / ".local/nas-ssh.json", timeout=240)
    assert result.returncode == 0, result.stderr[-1500:]
    record = json.loads(result.stdout)
    record.update(at=datetime.now(timezone.utc).isoformat(), comparison_commit=args.commit, acceptance_scope=scope)
    destination.write_text(json.dumps(record, indent=2) + "\n")
    (folder / "compose.release.json").write_text(json.dumps({"services": {
        name: {"image": identity} for name, identity in record["service_images"].items()}}, indent=2) + "\n")
    print(json.dumps({"images_pinned": True, "runner_restarted": True, "production_modified": False}), flush=True)


if __name__ == "__main__":
    main()
