"""Read comparison logs and archived receipts without burdening the test JVM.

Only the explicitly owned nested Jenkins volume is read. Large artifacts remain
in its archive; the local index records their size and SHA-256. This collector
does not execute Jenkins jobs or change their result.
"""

import argparse
import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import PurePosixPath

from deploy_nas_parity import CREDENTIALS
from nas_candidate_paths import comparison_source
from nas_ssh import run_script

PROGRAM = r"""
import base64,hashlib,json,pathlib,re,xml.etree.ElementTree as ET
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
root=pathlib.Path('/volume1/@docker/volumes/leroy-nas-parity_engine/_data/volumes/jenkins-parity-aligned-home/_data').resolve()
build=root/'jobs'/JOB/'builds'/str(NUMBER)
assert build.resolve().is_relative_to(root) and build.is_dir()
tree=ET.parse(build/'build.xml').getroot()
completed=tree.findtext('completed')=='true'
state={'number':NUMBER,'result':tree.findtext('result'),'building':not completed,
       'duration':int(tree.findtext('duration') or 0),'timestamp':int(tree.findtext('timestamp')),
       'revisions':sorted(set(e.text for e in tree.findall('.//lastBuiltRevision/SHA1')))}
console=(build/'log').read_text(errors='replace')
console=re.sub(r'\x1b\[8m.*?\x1b\[0m','',console)
state['checkout_revisions']=sorted(set(re.findall(r'Checking out Revision ([0-9a-f]{40})\b',console)))
artifacts=[]
copied=0
if completed:
 archive=build/'archive'
 for path in sorted(archive.rglob('*')):
  if not path.is_file():continue
  assert not path.is_symlink() and path.resolve().is_relative_to(archive.resolve())
  size=path.stat().st_size
  with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
  item={'name':path.relative_to(archive).as_posix(),'size':size,'sha256':digest}
  readable = path.suffix.lower() in {'.json','.xml','.txt','.log'} or path.name == 'artifacts.tar.gz'
  if readable and size<=8*1024*1024 and copied+size<=64*1024*1024:
   item['content']=base64.b64encode(path.read_bytes()).decode()
   copied+=size
  artifacts.append(item)
print(json.dumps({'build':state,'console':console,'artifacts':artifacts}))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pipeline")
    parser.add_argument("--build", type=int, default=1)
    parser.add_argument("--candidate")
    args = parser.parse_args()
    source, folder = comparison_source(args.pipeline, args.candidate)
    assert args.build > 0
    program = f"JOB={args.pipeline!r}\nNUMBER={args.build}\n" + PROGRAM
    result = run_script("python3 - <<'PY'\n" + program + "PY\n", CREDENTIALS, sudo=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr[-1500:])
    evidence = json.loads(result.stdout)
    prepared = json.loads((folder / "prepared.json").read_text())
    pair_path = folder / "pair.json"
    pair = (
        json.loads(pair_path.read_text())
        if pair_path.exists()
        else {
            "pipeline": args.pipeline,
            "commit": source["commit"],
            "parameters": prepared["parameters"],
            "application_patches_applied": source.get("application_patches_applied", False),
            "complete": False,
        }
    )
    previous = pair.get("jenkins", {})
    assert previous.get("number", args.build) == args.build, "Do not replace another build's evidence"
    pair["jenkins"] = evidence["build"]
    if source["commit"] and not evidence["build"]["building"]:
        assert source["commit"] in evidence["build"]["checkout_revisions"]
    pair["jenkins_evidence_source"] = "read-only owned comparison Jenkins volume"
    pair["recorded_at"] = datetime.now(timezone.utc).isoformat()
    for name in ("jenkins-console.log", f"jenkins-{args.build}-console.log"):
        (folder / name).write_text(evidence["console"], encoding="utf-8")
    archive = folder / f"jenkins-{args.build}-artifacts"
    for artifact in evidence["artifacts"]:
        content = artifact.pop("content", None)
        artifact["copied_locally"] = content is not None
        if content is None:
            continue
        name = PurePosixPath(artifact["name"])
        assert not name.is_absolute() and ".." not in name.parts
        destination = archive.joinpath(*name.parts)
        assert destination.resolve().is_relative_to(archive.resolve())
        value = base64.b64decode(content, validate=True)
        assert len(value) == artifact["size"]
        assert hashlib.sha256(value).hexdigest() == artifact["sha256"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(value)
    (folder / f"jenkins-{args.build}-artifact-index.json").write_text(
        json.dumps(evidence["artifacts"], indent=2) + "\n", encoding="utf-8"
    )
    pair_path.write_text(json.dumps(pair, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps({"pipeline": args.pipeline, **evidence["build"], "artifacts": len(evidence["artifacts"])})
    )


if __name__ == "__main__":
    main()
