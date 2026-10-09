"""Create private test mirrors at the inventoried commits, without touching other checkouts."""

import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
inventory = json.loads((root / "docs/jenkins-inventory.json").read_text(encoding="utf-8"))
sources = root / ".sources"
sources.mkdir(exist_ok=True)
for name, commit in inventory["repositories"].items():
    path = sources / name
    url = (
        "https://github.com/x0r3/antares.git"
        if name == "antares"
        else "http://192.168.178.97:3000/gitea-admin/" + name + ".git"
    )
    if not path.exists():
        subprocess.run(
            ["git", "-c", "credential.interactive=false", "clone", "--no-checkout", url, str(path)],
            check=True,
        )
        subprocess.run(["git", "-C", str(path), "checkout", "--detach", commit], check=True)
    actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"], text=True).strip()
    if actual != commit or dirty:
        raise SystemExit(
            f"Existing test checkout {name} differs from inventory; retained without modification"
        )
    print(name, actual)
