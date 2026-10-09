"""Replace only frontend assets in the owned NAS controller image."""

import argparse
import hashlib
import json
import tarfile
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE
from nas_ssh import ROOT, run_script, upload_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", choices=["route-loading", "detail-loading", "timeline-status"], default="route-loading")
    revision = parser.parse_args().revision
    marker = ROOT / f"test-results/nas-parity/{revision}-ui.json"
    if marker.exists():
        raise RuntimeError("This UI deployment is already recorded")
    with closing(client()) as api:
        for status in ("queued", "running", "waiting"):
            response = api.get("/api/runs", params={"status": status})
            response.raise_for_status()
            assert not response.json(), "Wait for active Leroy comparisons"
        assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
    assets = ROOT / "web/dist"
    hashes = {
        path.relative_to(assets).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in assets.rglob("*")
        if path.is_file()
    }
    assert "index.html" in hashes
    archive = LOCAL / f"ui-update-{revision}.tar"
    with tarfile.open(archive, "w") as bundle:
        bundle.add(ROOT / "infra/nas/Dockerfile.ui", "Dockerfile")
        bundle.add(assets, "dist")
    upload_file(archive, REMOTE + "/" + archive.name, CREDENTIALS)
    script = f"""set -eu
cd {REMOTE}
test -f .leroy-owned
test "$(docker inspect -f '{{{{index .Config.Labels "com.docker.compose.project"}}}}' leroy-nas-parity-controller-1)" = leroy-nas-parity
chmod 644 config/leroy.toml
docker tag "$(docker inspect -f '{{{{.Image}}}}' leroy-nas-parity-controller-1)" leroy-controller:nas-parity-before-{revision}
mkdir -p ui-update-{revision}
tar -xf {archive.name} -C ui-update-{revision}
docker build --network=none --pull=false --build-arg CONTROLLER_BASE=leroy-controller:nas-parity-before-{revision} -t leroy-controller:nas-parity-ui-{revision} ui-update-{revision}
docker tag leroy-controller:nas-parity-ui-{revision} leroy-controller:nas-parity
docker compose up -d --no-deps --wait --wait-timeout 120 controller
python3 - <<'PY'
import json,subprocess
def image(name):return json.loads(subprocess.check_output(['docker','image','inspect',name]))[0]
old=image('leroy-controller:nas-parity-before-{revision}')
new=image('leroy-controller:nas-parity-ui-{revision}')
assert old['Config']==new['Config']
assert new['RootFS']['Layers'][:-1]==old['RootFS']['Layers']
assert json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-controller-1']))[0]['Image']==new['Id']
print('EVIDENCE='+json.dumps({{'previous_image':old['Id'],'new_image':new['Id'],'same_backend_layers':True,'same_runtime_config':True}}))
PY
"""
    result = run_script(script, CREDENTIALS, timeout=300)
    if result.returncode:
        raise RuntimeError(result.stderr[-1800:])
    evidence = json.loads(
        next(line[9:] for line in result.stdout.splitlines() if line.startswith("EVIDENCE="))
    )
    evidence.update(at=datetime.now(timezone.utc).isoformat(), assets=hashes)
    with closing(client()) as api:
        for name, digest in hashes.items():
            response = api.get("/" if name == "index.html" else "/" + name)
            response.raise_for_status()
            assert hashlib.sha256(response.content).hexdigest() == digest, name
    evidence.update(served_assets_verified=True, http_readiness_verified=True)
    marker.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
