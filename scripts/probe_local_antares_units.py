"""Measure unchanged Antares unit gates with a bounded CPU budget in local Linux."""

import argparse
import hashlib
import json
import re
import subprocess
import time

from nas_ssh import ROOT
from probe_local_antares_candidate import DIN, inner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", default="9f05b7f1aa56d709f269c37700a65785385a8391")
    parser.add_argument("--cpus", type=int, choices=[2, 6], default=2)
    parser.add_argument("--memory", choices=["3g", "4g"], default="3g")
    parser.add_argument("--browser-proof", default="local-linux-browsers-full-four-gib.json")
    args = parser.parse_args()
    commit = args.candidate
    assert re.fullmatch(r"[a-f0-9]{40}", commit)
    assert re.fullmatch(r"local-linux-browsers-[a-z0-9-]+\.json", args.browser_proof)
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / commit
    proof = json.loads((folder / args.browser_proof).read_text())
    assert proof["commit"] == commit and proof["passed"]
    source = proof["workspace_volume"]
    suffix = "" if args.memory == "3g" else "-four-gib"
    volume = "leroy-antares-unit-cpu" + str(args.cpus) + "-" + commit[:12] + suffix + "-work"
    name = volume.removesuffix("-work")
    marker = folder / ("local-linux-unit-" + ("two" if args.cpus == 2 else "six") + "-cpu" + suffix + ".json")
    assert not marker.exists()
    assert volume not in inner("volume", "ls", "--format", "{{.Name}}").splitlines()
    outer = json.loads(subprocess.check_output(["docker", "inspect", DIN]))[0]
    assert outer["Config"]["Labels"]["com.docker.compose.project"] == "leroy-test"
    image = "mcr.microsoft.com/playwright:v1.61.1-noble"
    assert inner("image", "inspect", image, "--format", "{{.Id}}").strip() == proof["image_id"]
    inner("volume", "create", "--label", "io.leroy.antares-units=true", volume)
    program = r"""
set -eu
mkdir /work/repo
tar -C /source/repo --exclude='./test-results' --exclude='./playwright-report' --exclude='./coverage' -cf - . | tar -C /work/repo -xf -
cd /work/repo
python3 - <<'PY'
import hashlib,pathlib,tarfile,json
with tarfile.open('/input/source.tar') as archive:
 for member in archive:
  if not member.isfile():continue
  path=pathlib.Path('/work/repo')/member.name
  assert path.resolve().is_relative_to(pathlib.Path('/work/repo'))
  assert hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(archive.extractfile(member).read()).digest(),member.name
print('Every tracked source file matches the exact candidate archive',flush=True)
PY
node -e "console.log(JSON.stringify({node:process.version,availableParallelism:require('node:os').availableParallelism(),hostCpus:require('node:os').cpus().length}))"
npm test
"""
    command = [
        "docker", "exec", DIN, "docker", "run", "--name", name,
        "--label", "io.leroy.antares-units=true", "--init", "--network", "none",
        "--memory", args.memory, "--memory-swap", args.memory, "--cpus", str(args.cpus),
        "-v", source + ":/source:ro", "-v", volume + ":/work",
        "--mount", "type=bind,src=/sources/antares-nas-bundles/" + commit + ".tar,dst=/input/source.tar,readonly",
        "-e", "CI=true", "-e", "NODE_OPTIONS=--max-old-space-size=2048",
        image, "sh", "-c", program,
    ]
    started = time.time()
    with marker.with_suffix(".log").open("w", encoding="utf-8") as log:
        try:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=1200)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
    info = json.loads(inner("inspect", name))[0]
    assert info["Config"]["Labels"]["io.leroy.antares-units"] == "true"
    events = [json.loads(row) for row in inner(
        "events", "--since", str(int(started)), "--until", str(int(time.time()) + 1),
        "--filter", "container=" + info["Id"], "--filter", "event=oom", "--format", "{{json .}}",
    ).splitlines()]
    record = {
        "candidate": commit, "diagnostic_only": True, "nas_acceptance": False,
        "cpu_limit": args.cpus, "memory_limit": args.memory, "swap_enabled": False,
        "source_archive_sha256": hashlib.sha256(
            (ROOT / ".sources/antares-nas-bundles" / (commit + ".tar")).read_bytes()
        ).hexdigest(),
        "image": info["Image"], "returncode": code, "passed": code == 0,
        "duration_seconds": time.time() - started, "oom_events": events,
        "workspace_volume": volume, "container_state": info["State"],
    }
    marker.write_text(json.dumps(record, indent=2) + "\n")
    inner("rm", "-f", "-v", name)
    print(json.dumps(record), flush=True)
    assert code == 0, "Actual diagnostic failure retained"


if __name__ == "__main__":
    main()
