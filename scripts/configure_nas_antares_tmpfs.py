"""Apply the same optional, verified helper storage policy to both test engines."""

import argparse
import hashlib
import json
import re
import tomllib
import urllib.parse

from nas_followup_support import inner, jenkins_api, remote, start_jenkins, wait_production_jobs
from nas_gitea_target import idle
from nas_ssh import ROOT, upload_file
from verify_nas_antares_candidate import browser_counts, plain

CANDIDATE = "8607cfd438c7645012bf0482a5da83acb122d6dd"
SOURCE = "/fixtures/antares-docker.py"
TARGET = "/usr/local/bin/docker"

PROBE = r'''
import json,pathlib,shutil,subprocess,time
assert shutil.which('docker')==TARGET
def docker(*args):return subprocess.check_output(['docker',*args],text=True,timeout=30)
name='antares-ci-postgres-999999'
assert name not in docker('ps','-a','--format','{{.Names}}').splitlines()
docker('run','-d','--rm','--name',name,'--label','io.leroy.nas-parity=true','--network','none',
 '--memory','512m','--cpus','0.5','-e','POSTGRES_DB=antares_test','-e','POSTGRES_USER=antares',
 '-e','POSTGRES_PASSWORD=antares-test-password','postgres:18.4-alpine3.24')
try:
 for _ in range(30):
  ready=subprocess.run(['docker','exec',name,'pg_isready','-h','127.0.0.1','-U','antares','-d','antares_test'],capture_output=True,timeout=10)
  if ready.returncode==0:break
  time.sleep(1)
 else:raise TimeoutError('Disposable storage probe did not become ready')
 info=json.loads(docker('inspect',name))[0]
 assert info['HostConfig']['Tmpfs']=={'/var/lib/postgresql':'rw,nosuid,nodev,size=1g'}
 assert not [m for m in info['Mounts'] if m['Type']=='volume']
 values=docker('exec',name,'psql','-X','-qAt','-U','antares','-d','antares_test','-c',
  "SELECT name,setting FROM pg_settings WHERE name IN ('fsync','full_page_writes','synchronous_commit') ORDER BY name; CREATE TABLE policy_probe(value integer); INSERT INTO policy_probe VALUES (42); SELECT value FROM policy_probe").strip().splitlines()
 assert values==['fsync|on','full_page_writes|on','synchronous_commit|on','42'],values
 result={'tmpfs':info['HostConfig']['Tmpfs'],'durability':values[:3],'write_read_verified':True,
  'docker_version':docker('--version').strip()}
finally:docker('rm','-f','-v',name)
assert name not in docker('ps','-a','--format','{{.Names}}').splitlines()
result['helpers_removed']=True
print(json.dumps(result))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostic-only-reason", help="Explicitly compare original failing gates after retaining the full failed matrix")
    args = parser.parse_args()
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / CANDIDATE
    marker = folder / "tmpfs-policy-applied.json"
    assert not marker.exists(), "No implicit infrastructure reapplication"
    matrix = json.loads((folder / "focused-browsers-full-matrix-1g.json").read_text())
    assert matrix["helpers_removed"] and matrix["production_jobs_unchanged"]
    assert matrix["full_matrix_requested"] and matrix["commit"] == CANDIDATE
    console = plain((folder / "focused-browsers-full-matrix-1g.log").read_text(encoding="utf-8"))
    if args.diagnostic_only_reason:
        assert len(args.diagnostic_only_reason.strip()) >= 40 and not matrix["passed"]
        assert json.loads((folder / "focused-browsers-arena-ram-headroom.json").read_text())["helpers_removed"]
        assert (folder / "headroom-applied.json").is_file()
        counts = {name: int(count) for count, name in re.findall(r"^\s*(\d+) (passed|skipped|failed|flaky)\b", console, re.MULTILINE)}
        assert counts == {"failed": 2, "skipped": 3, "passed": 24}
    else:
        assert matrix["passed"], "Failed gates require an explicitly recorded diagnostic comparison"
        counts = browser_counts(console)
    source = ROOT / "infra/nas/antares-docker.py"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    proof = json.loads((marker.parents[3] / "antares-tmpfs-policy-tests.json").read_text())
    assert proof["passed"] and proof["tests"] == 13 and proof["sha256"] == digest
    wait_production_jobs()
    idle()
    assert not any(n.startswith("antares-") for n in inner("ps", "--format", "{{.Names}}").splitlines())
    config = ROOT / ".local/nas-parity/config/runner.toml"
    before = config.read_bytes()
    text = config.read_text()
    current = tomllib.loads(text)
    mount = "type=bind,source=" + SOURCE + ",target=" + TARGET + ",readonly"
    assert mount not in current["profiles"]["antares"]["mounts"]
    assert "LEROY_NAS_ANTARES_TMPFS" not in current["profiles"]["antares"]["environment"]
    first, rest = text.split("[profiles.antares.environment]", 1)
    line = next(line for line in first.splitlines() if line.startswith("mounts = "))
    first = first.replace(line, line[:-1] + ", " + json.dumps(mount) + "]")
    updated = first + '[profiles.antares.environment]\nLEROY_NAS_ANTARES_TMPFS = "1"\n' + rest
    expected = tomllib.loads(text)
    expected["profiles"]["antares"]["mounts"].append(mount)
    expected["profiles"]["antares"]["environment"]["LEROY_NAS_ANTARES_TMPFS"] = "1"
    assert tomllib.loads(updated) == expected
    staged = ROOT / ".local/nas-parity/runner-antares-tmpfs.toml"
    staged.write_text(updated)
    upload_file(source, "/volume1/docker/leroy-nas-parity/fixtures/antares-docker.py", ROOT / ".local/nas-ssh.json")
    remote("import pathlib\np=pathlib.Path('/volume1/docker/leroy-nas-parity/fixtures/antares-docker.py')\np.chmod(0o755)\n")
    start_jenkins()
    installation = r'''
import hashlib,pathlib,shutil,json
source=pathlib.Path(SOURCE);target=pathlib.Path(TARGET)
assert hashlib.sha256(source.read_bytes()).hexdigest()==EXPECTED
assert shutil.which('docker')=='/usr/bin/docker' and not target.exists() and not target.is_symlink()
target.symlink_to(source)
assert shutil.which('docker')==TARGET
print(json.dumps({'source_sha256':EXPECTED,'docker_cli':str(target)}))
'''
    try:
        prefix = f"SOURCE={SOURCE!r}\nTARGET={TARGET!r}\nEXPECTED={digest!r}\n"
        installed = json.loads(inner("exec", "jenkins-parity", "python3", "-c", prefix + installation))
        probes = {"jenkins": json.loads(inner("exec", "-e", "LEROY_NAS_ANTARES_TMPFS=1",
                                             "jenkins-parity", "python3", "-c", "TARGET=" + repr(TARGET) + "\n" + PROBE, timeout=180))}
        probes["leroy"] = json.loads(inner(
            "run", "--rm", "--network", "none", "--memory", "128m", "--cpus", "0.5",
            "--mount", mount, "--mount", "type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock",
            "-e", "LEROY_NAS_ANTARES_TMPFS=1", "leroy-job:nas-parity",
            "python", "-c", "TARGET=" + repr(TARGET) + "\n" + PROBE, timeout=180))
        assert probes["jenkins"] == probes["leroy"]
        script = '''import jenkins.model.Jenkins
import hudson.slaves.EnvironmentVariablesNodeProperty
def instance=Jenkins.get()
assert !instance.items.any { it.lastBuild?.building }
assert instance.queue.items.length==0
def property=instance.globalNodeProperties.get(EnvironmentVariablesNodeProperty)
assert property!=null && property.envVars.get('LEROY_NAS_ANTARES_TMPFS')==null
property.envVars.put('LEROY_NAS_ANTARES_TMPFS','1')
instance.save()
println('Owned temporary helper storage configured')
'''
        message = jenkins_api("/scriptText", urllib.parse.urlencode({"script": script}), "application/x-www-form-urlencoded")["text"]
        assert message.strip() == "Owned temporary helper storage configured", message
    finally:
        inner("stop", "--time", "120", "jenkins-parity", timeout=150)
    old_hash = hashlib.sha256(before).hexdigest()
    new_hash = hashlib.sha256(staged.read_bytes()).hexdigest()
    upload_file(staged, "/volume1/docker/leroy-nas-parity/config/runner-antares-tmpfs.toml", ROOT / ".local/nas-ssh.json")
    apply = r'''
import hashlib,pathlib,shutil,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
path=root/'config/runner.toml';staged=root/'config/runner-antares-tmpfs.toml'
assert hashlib.sha256(path.read_bytes()).hexdigest()==BEFORE and hashlib.sha256(staged.read_bytes()).hexdigest()==AFTER
backup=root/'config/runner-before-tmpfs.toml';assert not backup.exists()
shutil.copy2(path,backup);shutil.copyfile(staged,path);path.chmod(0o644)
subprocess.run(['docker','compose','up','-d','--no-deps','--force-recreate','runner'],cwd=root,check=True,capture_output=True,timeout=120)
'''
    remote(f"BEFORE={old_hash!r}\nAFTER={new_hash!r}\n" + apply, timeout=150)
    (ROOT / ".local/nas-parity/runner-before-tmpfs.toml").write_bytes(before)
    config.write_bytes(staged.read_bytes())
    record = {
        "candidate": CANDIDATE, "policy_sha256": digest, "installed": installed, "engines": probes,
        "browser_matrix": counts, "runner_before_sha256": old_hash, "runner_after_sha256": new_hash,
        "database_tmpfs": "/var/lib/postgresql:rw,nosuid,nodev,size=1g",
        "browser_tmpfs": "/tmp:rw,nosuid,nodev,size=1g",
        "other_profiles_unchanged": True, "jenkinsfile_and_application_sources_unchanged": True,
        "original_assertions_and_timeouts_unchanged": True, "dependencies_and_images_unchanged": True,
        "production_modified": False, "full_ci_acceptance": False,
        "diagnostic_only_reason": args.diagnostic_only_reason,
    }
    marker.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"same_policy_both": True, "durability_and_write_read_verified": True,
                      "full_ci_acceptance": False}), flush=True)


if __name__ == "__main__":
    main()
