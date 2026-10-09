"""Read the test publication through Leroy when NAS administration SSH is unavailable."""

import json
import time
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from compare_nas_job import collect_artifacts
from nas_ssh import ROOT

from leroy.schema import Pipeline, Step

INSPECT = r"""
import hashlib,json,pathlib,zipfile
root=pathlib.Path('/publication')
rows=[]
for path in root.glob('*.zip.json'):
 assert not path.is_symlink() and path.is_file()
 manifest=json.loads(path.read_text())
 assert manifest['sourceCommit']==COMMIT and manifest['buildTimestamp']==STAMP
 name=manifest['artifact']
 assert pathlib.PurePosixPath(name).name==name and name.endswith('.zip')
 payload=root/name
 assert not payload.is_symlink() and payload.is_file()
 with payload.open('rb') as stream:
  digest=hashlib.file_digest(stream,'sha256').hexdigest()
 assert payload.stat().st_size==manifest['sizeBytes'] and digest==manifest['sha256']
 latest=root/'graphato-desktop-latest.zip'
 assert not latest.is_symlink() and latest.is_file()
 with latest.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==digest
 with zipfile.ZipFile(payload) as portable:
  assert portable.testzip() is None
  names=portable.namelist()
  assert len(names)==5 and set(names)=={'Graphato.exe','Graphato.portable','GraphatoData/','README-portable.txt','build-info.json'}
  with portable.open('Graphato.exe') as executable:assert executable.read(2)==b'MZ'
  build=json.loads(portable.read('build-info.json'))
  assert all(build[k]==manifest[k] for k in build)
  files={p.filename:{'size':p.file_size,'sha256':hashlib.sha256(portable.read(p)).hexdigest()} for p in portable.infolist()}
 rows.append({'manifest':manifest,'files':files,'latest_matches':True,'crc_verified':True})
assert len(rows)==1
print(json.dumps(rows))
"""


def main():
    folder = ROOT / "test-results/nas-parity/aligned/graphato-ci"
    ci = json.loads((folder / "leroy-run.json").read_text())
    assert ci["status"] == "succeeded" and all(s["status"] == "succeeded" for s in ci["steps"])
    manifest = json.loads((folder / "leroy-artifacts/desktop/desktop-release-manifest.json").read_text())
    image = json.loads((ROOT / "test-results/nas-parity/lease-fix-deployment.json").read_text())["images"][
        "leroy-job:nas-parity"
    ]["after"]
    inspect = f"COMMIT={ci['commit']!r}\nSTAMP={manifest['buildTimestamp']!r}\n" + INSPECT
    program = f"""import json,pathlib,subprocess
assert subprocess.check_output(['docker','info','--format','{{{{.Name}}}}'],text=True).strip()=='7d029e17dc28', 'Wrong Docker daemon'
command=['docker','run','--rm','--name','leroy-publication-audit-{ci["id"]}',
 '--network','none','--read-only','--user','1000:10','--cap-drop','ALL',
 '--security-opt','no-new-privileges:true','--memory','128m','--memory-swap','128m',
 '--cpus','0.5','--pids-limit','64','--mount','type=bind,source=/leroy-graphato-releases,target=/publication,readonly',
 {image!r},'python','-c',{inspect!r}]
rows=json.loads(subprocess.check_output(command,text=True,timeout=120))
pathlib.Path('publication.json').write_text(json.dumps(rows,indent=2)+'\\n')
print('Published ZIP, latest alias, checksums, CRC and embedded build identity verified.')
"""
    spec = Pipeline(
        id="leroy-nas-diagnostics",
        name="NAS-Abnahme: Desktop-Paket",
        group="Abnahme",
        profile="graphato",
        enabled=False,
        timeout=240,
        steps=[
            Step(
                id="inspect",
                name="Veröffentlichtes Paket prüfen",
                command=["python", "-c", program],
                timeout=180,
                artifacts=["publication.json"],
            )
        ],
        source={"kind": "diagnostic", "comparison_run": ci["id"], "read_only_test_destination": True},
    )
    output = folder / "publication-audit"
    output.mkdir(exist_ok=True)
    marker = output / "run-id.json"
    with closing(client()) as api:
        if marker.exists():
            run_id = json.loads(marker.read_text())["id"]
        else:
            for status in ("queued", "running", "waiting"):
                response = api.get("/api/runs", params={"status": status})
                response.raise_for_status()
                assert not response.json(), "Wait for the comparison and its children to finish"
            response = api.get("/api/pipelines")
            response.raise_for_status()
            assert not any(p["enabled"] for p in response.json())
            existing = next((p for p in response.json() if p["id"] == spec.id), None)
            assert not existing or existing["spec"]["source"].get("kind") == "diagnostic"
            (output / "definition.json").write_text(spec.model_dump_json(indent=2))
            api.put("/api/pipelines/" + spec.id, json=spec.model_dump()).raise_for_status()
            response = api.post("/api/pipelines/" + spec.id + "/runs", json={"commit": ci["commit"]})
            response.raise_for_status()
            run_id = response.json()["id"]
            marker.write_text(json.dumps({"id": run_id}) + "\n")
        while True:
            response = api.get("/api/runs/" + run_id)
            response.raise_for_status()
            run = response.json()
            if run["status"] not in ("queued", "running", "waiting"):
                break
            time.sleep(3)
        (output / "run.json").write_text(json.dumps(run, indent=2) + "\n")
        log = api.get(f"/api/runs/{run_id}/logs/inspect")
        log.raise_for_status()
        (output / "console.log").write_text(log.json()["text"], encoding="utf-8")
        assert run["status"] == "succeeded", log.json()["text"][-1200:]
        collect_artifacts(api, run, output)
    state = json.loads((folder / "leroy-final-target-only-state.json").read_text())
    state["desktop_publication"] = json.loads(
        (output / "leroy-artifacts/inspect/publication.json").read_text()
    )
    state["publication_evidence"] = {
        "method": "Independent read-only container on the owned NAS test Docker daemon",
        "audit_run": run_id,
        "read_at": datetime.now(timezone.utc).isoformat(),
        "nas_administration_ssh_used": False,
    }
    (folder / "leroy-final-state.json").write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps(state["publication_evidence"]))


if __name__ == "__main__":
    main()
