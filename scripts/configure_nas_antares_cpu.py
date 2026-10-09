"""Restore the Antares job's two-CPU budget without changing its source or test gates."""

import hashlib
import json
import tomllib
from contextlib import closing

from compare_nas_antares import client
from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE
from nas_ssh import ROOT, run_script, upload_file


def main():
    marker = ROOT / "test-results/nas-parity/followup/antares-two-cpu.json"
    assert not marker.exists()
    proof = json.loads((marker.parent / "candidates/antares/9f05b7f1aa56d709f269c37700a65785385a8391/local-linux-unit-two-cpu.json").read_text())
    assert proof["passed"] and not proof["oom_events"]
    with closing(client()) as api:
        for status in ("queued", "running", "waiting"):
            response = api.get("/api/runs", params={"status": status})
            response.raise_for_status()
            assert not response.json(), "Wait for active NAS comparisons"
    config = LOCAL / "config/runner.toml"
    original = config.read_bytes()
    text = config.read_text()
    before, section = text.split("[profiles.antares]\n", 1)
    antares, after = section.split("[profiles.antares.environment]", 1)
    assert antares.count("cpus = 6\n") == 1
    updated = before + "[profiles.antares]\n" + antares.replace("cpus = 6\n", "cpus = 2\n") + "[profiles.antares.environment]" + after
    old, new = tomllib.loads(text), tomllib.loads(updated)
    old["profiles"]["antares"]["cpus"] = 2
    assert old == new and new["profiles"]["antares"]["memory"] == "3g"
    staged = LOCAL / "runner-antares-two-cpu.toml"
    staged.write_text(updated)
    old_hash = hashlib.sha256(original).hexdigest()
    new_hash = hashlib.sha256(staged.read_bytes()).hexdigest()
    upload_file(staged, REMOTE + "/config/runner-antares-two-cpu.toml", CREDENTIALS)
    program = r"""
import hashlib,json,pathlib,shutil,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
path=root/'config/runner.toml';staged=root/'config/runner-antares-two-cpu.toml'
assert hashlib.sha256(path.read_bytes()).hexdigest()==BEFORE
assert hashlib.sha256(staged.read_bytes()).hexdigest()==AFTER
info=json.loads(subprocess.check_output(['docker','exec','leroy-nas-parity-docker-1','docker','inspect','jenkins-parity']))[0]
assert info['Id']=='29e75d9173c95db4f448ac038f2593e1f556e7eb2bf49bde68cba911526f3226' and not info['State']['Running']
assert not subprocess.check_output(['docker','exec','leroy-nas-parity-docker-1','docker','ps','-aq','--filter','label=io.leroy.runner=runner-nas-parity'],text=True).strip()
backup=root/'config/runner-before-two-cpu.toml';assert not backup.exists();shutil.copy2(path,backup)
shutil.copyfile(staged,path);path.chmod(0o644)
subprocess.run(['docker','compose','up','-d','--no-deps','--force-recreate','runner'],cwd=root,check=True,timeout=120,stdout=subprocess.DEVNULL)
current=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-runner-1']))[0]
assert current['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' and current['State']['Running']
print(json.dumps({'cpus':2,'memory':'3g','before_sha256':BEFORE,'after_sha256':AFTER,'other_profiles_unchanged':True,'source_and_test_commands_unchanged':True,'runner_id':current['Id']}))
"""
    result = run_script("python3 - <<'PY'\nBEFORE=" + repr(old_hash) + "\nAFTER=" + repr(new_hash) + "\n" + program + "\nPY\n",
                        CREDENTIALS, timeout=180)
    assert result.returncode == 0, result.stderr[-1500:]
    evidence = json.loads(result.stdout)
    (LOCAL / "runner-before-two-cpu.toml").write_bytes(original)
    config.write_bytes(staged.read_bytes())
    marker.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
