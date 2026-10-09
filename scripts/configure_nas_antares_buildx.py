"""Use the same already-inventoried Buildx plugin in both isolated Antares engines."""

import hashlib
import json
import tomllib

from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE
from nas_followup_support import inner, remote, start_jenkins
from nas_gitea_target import idle
from nas_ssh import ROOT, upload_file

SOURCE = "/fixtures/graphato-tools/docker-config/cli-plugins/docker-buildx"
TARGET = "/usr/local/lib/docker/cli-plugins/docker-buildx"


def main():
    folder = ROOT / "test-results/nas-parity/followup/antares-buildx"
    folder.mkdir(exist_ok=True)
    assert not (folder / "applied.json").exists(), "No implicit infrastructure retry"
    idle()
    assert not any(name.startswith("antares-") for name in inner("ps", "--format", "{{.Names}}").splitlines())
    tools = json.loads((ROOT / "test-results/nas-parity/graphato-tools.json").read_text())
    expected = tools["sha256"]["docker-config/cli-plugins/docker-buildx"]
    config = LOCAL / "config/runner.toml"
    before = config.read_bytes()
    old = tomllib.loads(before.decode())
    mount = "type=bind,source=" + SOURCE + ",target=" + TARGET + ",readonly"
    assert mount not in old["profiles"]["antares"]["mounts"]
    section, rest = before.decode().split("[profiles.antares.environment]", 1)
    line = next(line for line in section.splitlines() if line.startswith("mounts = "))
    updated = section.replace(line, line[:-1] + ", " + json.dumps(mount) + "]") + "[profiles.antares.environment]" + rest
    parsed = tomllib.loads(updated)
    old["profiles"]["antares"]["mounts"].append(mount)
    assert parsed == old
    staged = LOCAL / "runner-antares-buildx.toml"
    staged.write_text(updated)
    hashes = [hashlib.sha256(value).hexdigest() for value in (before, staged.read_bytes())]
    start_jenkins()
    install = r'''
import hashlib,pathlib,subprocess,json
source=pathlib.Path(SOURCE);target=pathlib.Path(TARGET)
assert hashlib.sha256(source.read_bytes()).hexdigest()==EXPECTED
assert not target.exists() and not target.is_symlink()
target.parent.mkdir(parents=True,exist_ok=True);target.symlink_to(source)
print(json.dumps({'version':subprocess.check_output(['docker','buildx','version'],text=True).strip(),'sha256':EXPECTED}))
'''
    prefix = f"SOURCE={SOURCE!r}\nTARGET={TARGET!r}\nEXPECTED={expected!r}\n"
    installed = json.loads(inner("exec", "jenkins-parity", "python3", "-c", prefix + install))
    assert installed["version"] == tools["versions"]["buildx"]
    probe = r'''
import hashlib,json,pathlib,subprocess,tempfile
plugin=pathlib.Path(TARGET)
assert hashlib.sha256(plugin.read_bytes()).hexdigest()==EXPECTED
version=subprocess.check_output(['docker','buildx','version'],text=True).strip()
tag='leroy-buildx-probe:'+ENGINE
with tempfile.TemporaryDirectory(prefix='leroy-builder-') as directory:
 pathlib.Path(directory,'Dockerfile').write_text('FROM scratch\nLABEL io.leroy.buildx-probe=true\n')
 result=subprocess.run(['docker','build','--network=none','--tag',tag,directory],text=True,capture_output=True,timeout=120)
 assert result.returncode==0,result.stderr
 image=json.loads(subprocess.check_output(['docker','image','inspect',tag],text=True))[0]
 assert image['Config']['Labels']['io.leroy.buildx-probe']=='true'
 subprocess.run(['docker','image','rm',tag],check=True,capture_output=True)
 print(json.dumps({'version':version,'sha256':EXPECTED,'build_succeeded':True,'builder_output':result.stderr}))
'''
    proofs = {}
    try:
        proofs["jenkins"] = json.loads(inner("exec", "jenkins-parity", "python3", "-c", prefix + "ENGINE='jenkins'\n" + probe, timeout=150))
        proofs["leroy"] = json.loads(inner(
            "run", "--rm", "--network", "none", "--memory", "256m", "--cpus", "0.5",
            "--mount", mount, "-v", "/var/run/docker.sock:/var/run/docker.sock",
            "--entrypoint", "python3", "leroy-job:nas-parity", "-c", prefix + "ENGINE='leroy'\n" + probe, timeout=150,
        ))
    finally:
        inner("stop", "--time", "120", "jenkins-parity", timeout=150)
    assert proofs["jenkins"]["version"] == proofs["leroy"]["version"]
    upload_file(staged, REMOTE + "/config/runner-antares-buildx.toml", CREDENTIALS)
    program = r'''
import hashlib,pathlib,shutil,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
path=root/'config/runner.toml';staged=root/'config/runner-antares-buildx.toml'
assert hashlib.sha256(path.read_bytes()).hexdigest()==BEFORE
assert hashlib.sha256(staged.read_bytes()).hexdigest()==AFTER
backup=root/'config/runner-before-buildx.toml';assert not backup.exists()
shutil.copy2(path,backup);shutil.copyfile(staged,path);path.chmod(0o644)
subprocess.run(['docker','compose','up','-d','--no-deps','--force-recreate','runner'],cwd=root,check=True,capture_output=True,timeout=120)
'''
    remote(f"BEFORE={hashes[0]!r}\nAFTER={hashes[1]!r}\n" + program, timeout=150)
    (LOCAL / "runner-before-buildx.toml").write_bytes(before)
    config.write_bytes(staged.read_bytes())
    report = {
        "engines": proofs, "runner_config_before_sha256": hashes[0], "runner_config_after_sha256": hashes[1],
        "same_binary": True, "source_and_timeouts_changed": False, "production_modified": False,
        "reason": "Both previous comparisons used the legacy builder; expose the same already present Buildx plugin",
    }
    (folder / "applied.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"same_binary": True, "both_build_probes_passed": True}))


if __name__ == "__main__":
    main()
