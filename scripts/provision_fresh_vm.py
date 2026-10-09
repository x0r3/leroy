"""Use a new test disk while preserving the previous VM disk and its evidence."""

import json
import subprocess
import sys
import uuid
from contextlib import closing
from datetime import datetime, timezone

from test_support import ROOT, api
from vm import LOCAL

override = LOCAL / "fresh.compose.yaml"
if override.exists():
    raise SystemExit("A fresh test disk is already selected; refusing another replacement")
with closing(api()) as client:
    response = client.get("/api/pipelines")
    response.raise_for_status()
    for pipeline in response.json():
        if not pipeline["id"].startswith("graphato-"):
            continue
        for status in ("queued", "running", "waiting"):
            active = client.get(
                "/api/runs", params={"pipeline": pipeline["id"], "status": status, "limit": 1}
            )
            active.raise_for_status()
            if active.json():
                raise SystemExit("Wait for active Graphato jobs before provisioning a new VM")
inspection = json.loads(subprocess.check_output(["docker", "inspect", "leroy-linux-vm"]))[0]
previous = next(mount["Name"] for mount in inspection["Mounts"] if mount["Destination"] == "/vm")
assert previous.startswith("leroy-vm_")
subprocess.run([sys.executable, "scripts/vm.py", "stop"], cwd=ROOT, check=True)
name = "leroy-vm_acceptance-" + uuid.uuid4().hex[:12]
subprocess.run(["docker", "volume", "create", name], check=True)
override.write_text(json.dumps({"volumes": {"disk": {"name": name}}}), encoding="utf-8")
record = {
    "created_at": datetime.now(timezone.utc).isoformat(),
    "previous_disk_preserved": previous,
    "fresh_disk": name,
    "source": json.loads((LOCAL / "config/image.json").read_text(encoding="utf-8")),
    "reason": "Independent clean-room acceptance; previous runtime guard left untouched",
}
(ROOT / "test-results/vm/fresh-provision.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
subprocess.run([sys.executable, "scripts/vm.py", "start"], cwd=ROOT, check=True)
print(json.dumps(record), flush=True)
