"""Freeze Jenkins' actually built original Graphato revision, preserving the old baseline."""

import hashlib
import json
import subprocess
from contextlib import closing

from compare_nas_antares import client
from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE, remote
from nas_ssh import ROOT, connection

COMMIT = "48b741264f3b8353400649f6b05abf6a9c129233"
PREVIOUS = "ffd4be75f36f4590272832691df04b06ae9e388a"


def main():
    results = ROOT / "test-results/nas-parity"
    baseline_file = results / "baseline.json"
    baseline = json.loads(baseline_file.read_text())
    assert baseline["sources"]["graphato"]["commit"] == PREVIOUS
    assert all(
        not p.get("leroy_run") and not p.get("jenkins_run")
        for p in baseline["pipelines"]
        if p["pipeline"].startswith("graphato-")
    )
    previous = results / "baseline-before-live-graphato.json"
    if not previous.exists():
        previous.write_bytes(baseline_file.read_bytes())
    remote(
        f"""cd {REMOTE}
test -f .leroy-owned
test "$(docker exec jenkins git -C /var/jenkins_home/workspace/graphato-ci rev-parse HEAD)" = {COMMIT}
mkdir -p exports
docker run --rm --network none --memory 256m --cpus 0.5 \
 -v /volume1/docker/jenkins/workspace/graphato-ci:/source:ro -v {REMOTE}/exports:/output \
 --entrypoint git leroy-job:nas-parity -c safe.directory=/source -C /source bundle create /output/graphato-current.bundle HEAD
docker run --rm --network none --memory 256m --cpus 0.5 \
 -v {REMOTE}/sources/graphato:/target -v {REMOTE}/exports:/input:ro \
 --entrypoint sh leroy-job:nas-parity -c 'git -c safe.directory=/target --git-dir=/target update-ref refs/heads/nas-inventory-original {PREVIOUS} && git -c safe.directory=/target --git-dir=/target fetch /input/graphato-current.bundle HEAD && git -c safe.directory=/target --git-dir=/target update-ref refs/heads/master {COMMIT}'
""",
        timeout=600,
    )
    settings, args, env = connection(CREDENTIALS)
    bundle = LOCAL / "graphato-current.bundle"
    with bundle.open("wb") as output:
        result = subprocess.run(
            [
                *args,
                settings["username"] + "@" + settings["host"],
                "cat " + REMOTE + "/exports/graphato-current.bundle",
            ],
            stdout=output,
            stderr=subprocess.PIPE,
            env=env,
            timeout=600,
        )
    if result.returncode:
        raise RuntimeError("Could not download the owned original-source Git bundle")
    checkout = ROOT / ".sources/graphato-nas-original"
    if checkout.exists():
        raise RuntimeError("Original NAS checkout already exists; inspect before retrying")
    subprocess.run(["git", "init", str(checkout)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(checkout), "fetch", str(bundle), "HEAD"], check=True)
    subprocess.run(["git", "-C", str(checkout), "checkout", "--detach", COMMIT], check=True)

    def git(*args):
        return subprocess.check_output(["git", "-C", str(checkout), *args])

    assert not git("status", "--porcelain").strip()
    baseline["sources"]["graphato"] = {
        "commit": COMMIT,
        "tree": git("rev-parse", "HEAD^{tree}").decode().strip(),
        "application_patches_applied": False,
        "local_checkout": ".sources/graphato-nas-original",
        "previous_inventory_commit": PREVIOUS,
        "selected_from": "production Jenkins graphato-ci build 4",
    }
    for job in baseline["pipelines"]:
        if job["repository"] == "graphato":
            sha = hashlib.sha256(git("show", COMMIT + ":" + job["script_path"])).hexdigest()
            assert sha == job["script_sha256"], "Review changed Jenkinsfile before reusing migration"
            job["commit"] = COMMIT
    baseline_file.write_text(json.dumps(baseline, indent=2) + "\n")
    record = {
        "previous": PREVIOUS,
        "selected": COMMIT,
        "commits": git("log", "--format=%h %s", PREVIOUS + ".." + COMMIT).decode().splitlines(),
        "jenkinsfiles_unchanged": True,
        "application_patches_applied": False,
        "bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
    }
    (results / "graphato-live-source.json").write_text(json.dumps(record, indent=2) + "\n")
    with closing(client()) as api:
        for pipeline in api.get("/api/pipelines").json():
            if pipeline["id"].startswith("graphato-") and pipeline["id"] != "graphato-bootstrap-host":
                spec = pipeline["spec"]
                spec["source"]["commit"] = COMMIT
                api.put("/api/pipelines/" + pipeline["id"], json=spec).raise_for_status()
    print("Frozen original Graphato revision used by production Jenkins:", COMMIT)


if __name__ == "__main__":
    main()
