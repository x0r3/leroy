"""Record lease age and step progress for the current explicit comparison attempt."""

import json
import time
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from nas_ssh import ROOT


def main():
    folder = ROOT / "test-results/nas-parity/aligned/graphato-ci"
    run_id = json.loads((folder / "pair.json").read_text())["leroy_run"]
    output = folder / ("lease-observations-" + run_id + ".jsonl")
    with closing(client()) as api, output.open("a", encoding="utf-8") as stream:
        while True:
            start = time.monotonic()
            response = api.get("/api/runs/" + run_id)
            response.raise_for_status()
            run = response.json()
            stamp = datetime.now(timezone.utc)
            remaining = (
                (datetime.fromisoformat(run["lease_until"]) - stamp).total_seconds()
                if run.get("lease_until")
                else None
            )
            row = {
                "at": stamp.isoformat(),
                "run": run_id,
                "status": run["status"],
                "request_seconds": round(time.monotonic() - start, 3),
                "lease_remaining_seconds": remaining,
                "steps": {s["id"]: s["status"] for s in run["steps"]},
            }
            stream.write(json.dumps(row) + "\n")
            stream.flush()
            print(
                json.dumps(
                    {
                        "at": row["at"],
                        "status": row["status"],
                        "active": [name for name, status in row["steps"].items() if status == "running"],
                        "lease_seconds": remaining,
                    }
                ),
                flush=True,
            )
            if run["status"] not in ("queued", "running", "waiting"):
                return
            time.sleep(30)


if __name__ == "__main__":
    main()
