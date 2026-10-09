"""Copy production image bytes into the owned daemon and verify their identity."""

import json
import re

from deploy_nas_parity import CREDENTIALS, remote
from nas_ssh import ROOT, run_script

OUTPUT = ROOT / "test-results/nas-parity/images"
CONFIG_KEYS = (
    "Env",
    "Cmd",
    "Entrypoint",
    "User",
    "WorkingDir",
    "Volumes",
    "Labels",
    "Healthcheck",
    "ExposedPorts",
    "StopSignal",
)


def inspect(identity, nested=False):
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", identity)
    prefix = "docker exec leroy-nas-parity-docker-1 " if nested else ""
    result = run_script(prefix + "docker image inspect " + identity + "\n", CREDENTIALS)
    if result.returncode:
        raise RuntimeError("Image inspection failed: " + result.stderr)
    value = json.loads(result.stdout)[0]
    return {
        "id": value["Id"],
        "layers": value["RootFS"]["Layers"],
        "config": {key: value["Config"].get(key) for key in CONFIG_KEYS},
    }


def import_production_image(name):
    assert name in {"gitea", "paperless", "paperless-db", "paperless-redis"}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    marker = OUTPUT / (name + ".json")
    if marker.exists():
        saved = json.loads(marker.read_text())
        assert inspect(saved["nested_id"], nested=True)["layers"] == saved["layers"]
        return saved
    result = run_script("docker inspect --format '{{.Image}}' " + name + "\n", CREDENTIALS)
    if result.returncode:
        raise RuntimeError("Production image identity inspection failed")
    identity = result.stdout.strip()
    source = inspect(identity)
    output = remote(
        f"docker image save {identity} | docker exec -i leroy-nas-parity-docker-1 docker load\n",
        timeout=900,
    )
    loaded = re.findall(r"Loaded image ID: (sha256:[0-9a-f]{64})", output)
    assert len(loaded) == 1, "Expected one imported image identity"
    target = inspect(loaded[0], nested=True)
    assert source["layers"] == target["layers"], "Image filesystem layers differ"
    assert source["config"] == target["config"], "Image runtime configuration differs"
    saved = {
        "production_id": identity,
        "nested_id": target["id"],
        "layers": target["layers"],
        "filesystem_layers_equal": True,
        "runtime_configuration_equal": True,
    }
    marker.write_text(json.dumps(saved, indent=2) + "\n")
    return saved
