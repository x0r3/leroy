"""Preserve browser failure summaries and selected traces from the owned workspace."""

import argparse
import base64
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath

from nas_ssh import ROOT, run_script


def artifact_path(folder, name):
    name = PurePosixPath(name)
    assert not name.is_absolute() and ".." not in name.parts
    assert all(":" not in part and "\\" not in part for part in name.parts)
    path = folder.joinpath(*name.parts).resolve()
    assert path.is_relative_to(folder.resolve())
    if os.name == "nt":
        resolved = str(path)
        path = Path("\\\\?\\UNC\\" + resolved[2:] if resolved.startswith("\\\\") else "\\\\?\\" + resolved)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--trace", action="append", default=[])
    parser.add_argument("--result-directory", default="playwright",
                        help="Recorded diagnostic artifact directory below the owned workspace test-results")
    args = parser.parse_args()
    assert re.fullmatch(r"[a-f0-9]{40}", args.candidate)
    assert re.fullmatch(r"[a-z0-9-]{1,24}", args.attempt)
    assert args.result_directory in {"playwright", "playwright-" + args.attempt}
    program = r"""
import base64,hashlib,json,pathlib,subprocess
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
workspace=pathlib.Path('/volume1/@docker/volumes/leroy-nas-parity_engine/_data/volumes/jenkins-parity-aligned-home/_data/workspace/antares-ci')
assert (workspace/'.git/HEAD').read_text().strip()==COMMIT
root=workspace/'test-results'/DIRECTORY;rows=[];copied=0
assert root.resolve().is_relative_to((workspace/'test-results').resolve())
for path in sorted(root.rglob('*')):
 if not path.is_file() or path.name not in ['error-context.md','test-failed-1.png','trace.zip']:continue
 assert not path.is_symlink() and path.resolve().is_relative_to(root.resolve())
 size=path.stat().st_size
 with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
 name=path.relative_to(root).as_posix()
 copy=path.name!='trace.zip' or any(pattern in name for pattern in TRACES)
 row={'name':name,'size':size,'sha256':digest,'copied':copy}
 if copy:
  assert size<128*1024*1024 and copied+size<512*1024*1024
  row['content']=base64.b64encode(path.read_bytes()).decode();copied+=size
 rows.append(row)
print(json.dumps(rows))
"""
    result = run_script(
        "python3 - <<'PY'\nCOMMIT="
        + repr(args.candidate)
        + "\nTRACES="
        + repr(args.trace)
        + "\nDIRECTORY="
        + repr(args.result_directory)
        + "\n"
        + program
        + "\nPY\n",
        ROOT / ".local/nas-ssh.json",
        sudo=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-1500:]
    rows = json.loads(result.stdout)
    folder = (
        ROOT
        / "test-results/nas-parity/followup/candidates/antares"
        / args.candidate
        / ("browser-failures-" + args.attempt)
    )
    folder.mkdir(exist_ok=True)
    for row in rows:
        value = row.pop("content", None)
        if value is None:
            continue
        path = artifact_path(folder, row["name"])
        data = base64.b64decode(value, validate=True)
        assert len(data) == row["size"] and hashlib.sha256(data).hexdigest() == row["sha256"]
        if path.exists():
            assert path.read_bytes() == data, "Retain different attempts separately"
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    (folder / "index.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps({"files": len(rows), "copied": sum(row["copied"] for row in rows)}))


if __name__ == "__main__":
    main()
