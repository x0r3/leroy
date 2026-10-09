"""Create and verify a coherent NAS test backup, retaining its key locally."""

import argparse
import json
import re
import secrets
from contextlib import closing

from compare_nas_antares import client
from nas_followup_support import remote
from nas_ssh import ROOT, upload_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", help="Retain a separate backup/restore proof for a later accepted stack revision")
    args = parser.parse_args()
    folder = ROOT / "test-results/nas-parity/followup/nas-backup"
    if args.attempt:
        assert re.fullmatch(r"[a-z0-9-]{1,64}", args.attempt)
        folder = folder / "attempts" / args.attempt
    folder.mkdir(parents=True, exist_ok=True)
    assert not (folder / "started.json").exists(), "Inspect previous backup before another attempt"
    with closing(client()) as api:
        for status in ("queued", "running", "waiting"):
            assert not api.get("/api/runs", params={"status": status}).json()
        assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
    key = ROOT / ".local/nas-parity/backup-test-key"
    if not key.exists():
        key.write_text(secrets.token_urlsafe(48) + "\n")
    upload_file(key, "/volume1/docker/leroy-nas-parity/backup-test-key", ROOT / ".local/nas-ssh.json")
    (folder / "started.json").write_text(
        json.dumps({"key": str(key.relative_to(ROOT)), "scope": "owned test stack"}) + "\n"
    )
    result = json.loads(remote((ROOT / "infra/nas/verify-backup.py").read_text(), timeout=1200))
    (folder / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
