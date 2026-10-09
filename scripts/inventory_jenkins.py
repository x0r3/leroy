"""Read live Jenkins definitions without modifying jobs or revealing credentials."""

import argparse
import base64
import hashlib
import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--credentials-env", type=Path, required=True)
    p.add_argument("--output", type=Path, default=Path(".sources/jenkins"))
    args = p.parse_args()
    values = {}
    for line in args.credentials_env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            values[k] = v.strip().strip('"').strip("'")
    auth = base64.b64encode(
        (values["JENKINS_ADMIN_ID"] + ":" + values["JENKINS_ADMIN_PASSWORD"]).encode()
    ).decode()

    def get(path):
        request = urllib.request.Request(
            args.url.rstrip("/") + path, headers={"Authorization": "Basic " + auth}
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read()

    jobs = json.loads(get("/api/json?tree=jobs[name,color]"))["jobs"]
    args.output.mkdir(parents=True, exist_ok=True)
    inventory = []
    for job in jobs:
        raw = get("/job/" + job["name"] + "/config.xml")
        root = ET.fromstring(raw)
        (args.output / (job["name"] + ".xml")).write_bytes(raw)
        item = dict(
            job,
            sha256=hashlib.sha256(raw).hexdigest(),
            repositories=[x.text for x in root.findall(".//hudson.plugins.git.UserRemoteConfig/url")],
            branches=[x.text for x in root.findall(".//hudson.plugins.git.BranchSpec/name")],
            script_paths=[x.text for x in root.findall(".//scriptPath")],
            schedules=[x.text for x in root.findall(".//spec")],
            parameters=[x.text for x in root.findall(".//parameterDefinitions/*/name")],
            disabled=root.findtext("disabled"),
        )
        inventory.append(item)
        print(json.dumps(item))
    (args.output / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")


if __name__ == "__main__":
    main()
