"""Expose the same already-inventoried Compose binary to both Antares engines."""

import hashlib
import json
import tomllib

from nas_followup_support import inner, remote, start_jenkins
from nas_gitea_target import idle
from nas_ssh import ROOT, upload_file

SOURCE = "/fixtures/graphato-tools/docker-config/cli-plugins/docker-compose"
TARGET = "/usr/local/lib/docker/cli-plugins/docker-compose"


def main():
    folder = ROOT / "test-results/nas-parity/followup/antares-compose"
    folder.mkdir(exist_ok=True)
    assert not (folder / "applied.json").exists(), "Inspect existing tool evidence before repeating setup"
    idle()
    tools = json.loads((ROOT / "test-results/nas-parity/graphato-tools.json").read_text())
    expected = tools["sha256"]["docker-config/cli-plugins/docker-compose"]
    start_jenkins()
    program = r"""
import hashlib,json,pathlib,subprocess
source=pathlib.Path(SOURCE);target=pathlib.Path(TARGET)
assert source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest()==EXPECTED
assert not target.exists() and not target.is_symlink()
target.parent.mkdir(parents=True,exist_ok=True)
target.symlink_to(source)
version=subprocess.check_output(['docker','compose','version'],text=True).strip()
subprocess.run(['docker','compose','config','--quiet'],cwd='/var/jenkins_home/workspace/antares-ci',check=True,capture_output=True)
print(json.dumps({'version':version,'sha256':EXPECTED,'compose_config_passed':True}))
"""
    program = f"SOURCE={SOURCE!r}\nTARGET={TARGET!r}\nEXPECTED={expected!r}\n" + program
    jenkins = json.loads(inner("exec", "jenkins-parity", "python3", "-c", program))
    config = ROOT / ".local/nas-parity/config/runner.toml"
    before = config.read_bytes()
    text = config.read_text()
    parsed = tomllib.loads(text)
    assert parsed["profiles"]["antares"]["mounts"] == ["type=bind,source=/sources,target=/sources,readonly"]
    first, rest = text.split("[profiles.image-builds]", 1)
    old = 'mounts = ["type=bind,source=/sources,target=/sources,readonly"]'
    assert first.count(old) == 1
    mount = "type=bind,source=" + SOURCE + ",target=" + TARGET + ",readonly"
    first = first.replace(old, old[:-1] + ", " + json.dumps(mount) + "]")
    updated = first + "[profiles.image-builds]" + rest
    after = tomllib.loads(updated)
    assert {k: v for k, v in after["profiles"].items() if k != "antares"} == {
        k: v for k, v in parsed["profiles"].items() if k != "antares"
    }
    (ROOT / ".local/nas-parity/runner-before-antares-compose.toml").write_bytes(before)
    config.write_text(updated)
    upload_file(config, "/volume1/docker/leroy-nas-parity/config/runner.toml", ROOT / ".local/nas-ssh.json")
    remote(
        "import pathlib,subprocess\npathlib.Path('/volume1/docker/leroy-nas-parity/config/runner.toml').chmod(0o644)\n"
        "subprocess.run(['docker','restart','leroy-nas-parity-runner-1'],check=True,capture_output=True,timeout=90)\n"
    )
    leroy_version = inner(
        "run",
        "--rm",
        "--network",
        "none",
        "--memory",
        "128m",
        "--cpus",
        "0.5",
        "--mount",
        mount,
        "--entrypoint",
        "docker",
        "leroy-job:nas-parity",
        "compose",
        "version",
    ).strip()
    assert leroy_version == jenkins["version"] == tools["versions"]["compose"]
    report = {
        "jenkins": jenkins,
        "leroy_version": leroy_version,
        "same_binary": True,
        "production_modified": False,
        "application_commit_changed": False,
        "runner_config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
    }
    (folder / "applied.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
