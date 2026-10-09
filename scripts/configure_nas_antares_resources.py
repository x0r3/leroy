"""Apply the measured Antares budget symmetrically and restore Jenkins afterwards."""

import argparse
import json
import tomllib
import urllib.parse
from contextlib import closing

from compare_nas_antares import client
from nas_followup_support import inner, jenkins_api, remote, start_jenkins
from nas_ssh import ROOT, upload_file

FOLDER = ROOT / "test-results/nas-parity/followup/antares-resources"
VALUE = "--max-old-space-size=2048"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["apply", "restore-jenkins"])
    phase = parser.parse_args().phase
    FOLDER.mkdir(exist_ok=True)
    with closing(client()) as api:
        for status in ("queued", "running", "waiting"):
            assert not api.get("/api/runs", params={"status": status}).json()
        assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
    assert json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}")) is False
    if phase == "apply":
        assert not (FOLDER / "applied.json").exists()
        config = ROOT / ".local/nas-parity/config/runner.toml"
        original = config.read_bytes()
        text = config.read_text()
        current = tomllib.loads(text)
        assert (
            current["profiles"]["antares"]["memory"] == "2g"
            and "environment" not in current["profiles"]["antares"]
        )
        first, rest = text.split("[profiles.image-builds]", 1)
        first = first.replace('memory = "2g"', 'memory = "3g"', 1)
        text = (
            first
            + '[profiles.antares.environment]\nNODE_OPTIONS = "'
            + VALUE
            + '"\n\n[profiles.image-builds]'
            + rest
        )
        parsed = tomllib.loads(text)
        assert {k: v for k, v in parsed["profiles"].items() if k != "antares"} == {
            k: v for k, v in current["profiles"].items() if k != "antares"
        }
        (ROOT / ".local/nas-parity/runner-before-antares-memory.toml").write_bytes(original)
        config.write_text(text)
        upload_file(
            config, "/volume1/docker/leroy-nas-parity/config/runner.toml", ROOT / ".local/nas-ssh.json"
        )
        remote(
            "import pathlib,subprocess\npathlib.Path('/volume1/docker/leroy-nas-parity/config/runner.toml').chmod(0o644)\nsubprocess.run(['docker','restart','leroy-nas-parity-runner-1'],check=True,capture_output=True,timeout=90)\n"
        )
        inner("update", "--memory", "3g", "--memory-swap", "4g", "jenkins-parity")
    else:
        assert (FOLDER / "applied.json").exists() and not (FOLDER / "jenkins-restored.json").exists()
    start_jenkins()
    script = """import jenkins.model.Jenkins
import hudson.slaves.EnvironmentVariablesNodeProperty
def instance=Jenkins.get()
assert !instance.items.any { it.lastBuild?.building }
def property=instance.globalNodeProperties.get(EnvironmentVariablesNodeProperty)
assert property!=null
"""
    if phase == "apply":
        script += (
            "assert property.envVars.get('NODE_OPTIONS')==null\nproperty.envVars.put('NODE_OPTIONS','"
            + VALUE
            + "')\n"
        )
    else:
        script += (
            "assert property.envVars.get('NODE_OPTIONS')=='"
            + VALUE
            + "'\nproperty.envVars.remove('NODE_OPTIONS')\n"
        )
    script += "instance.save()\nprintln('Owned Antares budget updated')\n"
    output = jenkins_api(
        "/scriptText", urllib.parse.urlencode({"script": script}), "application/x-www-form-urlencoded"
    )["text"]
    assert output.strip() == "Owned Antares budget updated", output
    inner("stop", "jenkins-parity", timeout=240)
    if phase == "restore-jenkins":
        inner("update", "--memory", "2g", "--memory-swap", "4g", "--cpus", "2", "jenkins-parity")
    report = {
        "phase": phase,
        "antares_container_memory": "3g",
        "antares_node_options": VALUE,
        "cpu_limit": 2,
        "outer_memory_limit_changed": False,
        "jenkins_budget_restored": phase == "restore-jenkins",
        "jenkinsfile_or_assertions_changed": False,
    }
    (FOLDER / ("applied.json" if phase == "apply" else "jenkins-restored.json")).write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
