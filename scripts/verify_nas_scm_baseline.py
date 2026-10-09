"""Exercise the guarded handoff tool on the NAS in read-only preview mode."""

import argparse
import hashlib
import json
import re
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from nas_gitea_target import idle
from nas_ssh import ROOT, run_script, upload_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    assert re.fullmatch(r"[a-f0-9]{40}", args.commit)
    folder = ROOT / "test-results/nas-parity/followup/candidates/graphato" / args.commit
    assert (folder / "scenarios/root-private-existing-host/analysis.json").is_file()
    destination = folder / "scm-baseline-nas-preview.json"
    assert not destination.exists()
    proof = json.loads((folder.parents[2] / "cutover-preparation/scm-baseline-tests.json").read_text())
    assert proof["passed"] and proof["postgresql_real"] and proof["test_count"] >= 9
    script = ROOT / "scripts/prepare_scm_baseline.py"
    expected = hashlib.sha256(script.read_bytes()).hexdigest()
    assert expected == proof["script_sha256"]
    idle()
    selected = {}
    with closing(client()) as api:
        for pipeline in ["graphato-ci", "home-lab-ci", "nikicas-hub-ci"]:
            response = api.get("/api/runs", params={"pipeline": pipeline, "status": "succeeded", "limit": 1})
            response.raise_for_status()
            run, = response.json()
            assert re.fullmatch(r"[a-f0-9]{40}", run["commit"])
            selected[pipeline] = {"commit": run["commit"], "run": run["id"]}
    program = r'''
import pathlib,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
folder=root/'operations'
assert not folder.is_symlink()
folder.mkdir(mode=0o700,exist_ok=True)
assert folder.resolve().is_relative_to(root.resolve())
'''
    result = run_script("python3 - <<'PY'\n" + program + "\nPY\n", ROOT / ".local/nas-ssh.json", timeout=30)
    assert result.returncode == 0, result.stderr[-1000:]
    upload_file(script, "/volume1/docker/leroy-nas-parity/operations/prepare_scm_baseline.py", ROOT / ".local/nas-ssh.json")
    program = r'''
import hashlib,json,pathlib,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
script=root/'operations/prepare_scm_baseline.py';assert hashlib.sha256(script.read_bytes()).hexdigest()==EXPECTED
script.chmod(0o600)
info=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-controller-1'],text=True))[0]
assert info['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
rows={}
for pipeline,value in SELECTED.items():
 result=subprocess.run(['docker','exec','-i',info['Id'],'python','-',pipeline,'--commit',value['commit']],
  input=script.read_bytes(),capture_output=True,timeout=45)
 assert result.returncode==0,result.stderr.decode(errors='replace')[-1000:]
 row=json.loads(result.stdout)
 assert row['successful_run']==value['run'] and not row['applied'] and not row['changed']
 assert row['pipeline_remains_disabled'] and not row['run_created'] and not row['target_modified']
 rows[pipeline]=row
print(json.dumps({'passed':True,'previews':rows,'scm_baselines_applied':False,
 'triggers_activated':False,'production_modified':False,'script_sha256':EXPECTED}))
'''
    values = "SELECTED=" + repr(selected) + "\nEXPECTED=" + repr(expected) + "\n"
    result = run_script("python3 - <<'PY'\n" + values + program + "\nPY\n", ROOT / ".local/nas-ssh.json", timeout=180)
    assert result.returncode == 0, result.stderr[-1000:]
    record = json.loads(result.stdout)
    record.update(at=datetime.now(timezone.utc).isoformat(), comparison_commit=args.commit)
    destination.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"passed": True, "pipelines": list(record["previews"]), "scm_baselines_applied": False}), flush=True)


if __name__ == "__main__":
    main()
