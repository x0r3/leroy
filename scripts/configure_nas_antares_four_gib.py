"""Apply the measured four-GiB Antares job limit; keep the daemon bound unchanged."""

import hashlib
import json
import tomllib

from nas_followup_support import inner, remote
from nas_gitea_target import idle
from nas_ssh import ROOT, upload_file

CANDIDATE = "58da3ef5d112f58bc0a3d1cbd75179eb71d421c1"


def main():
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / CANDIDATE
    marker = folder / "four-gib-job-budget.json"
    assert not marker.exists(), "No implicit profile reapplication"
    proof = json.loads((folder / "local-linux-unit-six-cpu-four-gib.json").read_text())
    assert proof["candidate"] == CANDIDATE and proof["passed"] and not proof["oom_events"]
    assert proof["memory_limit"] == "4g" and proof["cpu_limit"] == 6
    idle()
    assert not json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}"))
    config = ROOT / ".local/nas-parity/config/runner.toml"
    before = config.read_bytes()
    text = config.read_text()
    prefix, body = text.split("[profiles.antares]\n", 1)
    section, suffix = body.split("[profiles.antares.environment]", 1)
    assert section.count('memory = "3g"\n') == 1
    updated = prefix + "[profiles.antares]\n" + section.replace('memory = "3g"\n', 'memory = "4g"\n') + "[profiles.antares.environment]" + suffix
    expected = tomllib.loads(text)
    expected["profiles"]["antares"]["memory"] = "4g"
    assert tomllib.loads(updated) == expected and expected["profiles"]["antares"]["cpus"] == 6
    staged = ROOT / ".local/nas-parity/runner-antares-four-gib.toml"
    staged.write_text(updated)
    upload_file(staged, "/volume1/docker/leroy-nas-parity/config/runner-antares-four-gib.toml", ROOT / ".local/nas-ssh.json")
    program = r'''
import hashlib,json,pathlib,shutil,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
parent=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-docker-1'],text=True))[0]
assert parent['Id']=='7d029e17dc28b04ec41ac927360062f057c97564227c62e7e01a50a4938b5a00'
assert parent['HostConfig']['Memory']==parent['HostConfig']['MemorySwap']==int(4.5*1024**3)
assert not subprocess.check_output(['docker','exec',parent['Id'],'docker','ps','-q','--filter','label=io.leroy.runner=runner-nas-parity'],text=True).strip()
path=root/'config/runner.toml';staged=root/'config/runner-antares-four-gib.toml'
assert hashlib.sha256(path.read_bytes()).hexdigest()==BEFORE and hashlib.sha256(staged.read_bytes()).hexdigest()==AFTER
backup=root/'config/runner-before-four-gib.toml';assert not backup.exists();shutil.copy2(path,backup)
shutil.copyfile(staged,path);path.chmod(0o644)
subprocess.run(['docker','compose','up','-d','--no-deps','--force-recreate','runner'],cwd=root,check=True,capture_output=True,timeout=120)
print(json.dumps({'candidate':CANDIDATE,'job_memory':'4g','job_cpus':6,'node_heap':'2g',
 'shared_daemon_memory':'4.5g','shared_daemon_additional_swap':False,'daemon_restarted':False,
 'before_sha256':BEFORE,'after_sha256':AFTER,'other_profiles_unchanged':True,
 'jenkins_budget_applied_only_during_comparison':True,'production_modified':False,'full_ci_acceptance':False}))
'''
    old_hash = hashlib.sha256(before).hexdigest()
    new_hash = hashlib.sha256(staged.read_bytes()).hexdigest()
    record = json.loads(remote(f"BEFORE={old_hash!r}\nAFTER={new_hash!r}\nCANDIDATE={CANDIDATE!r}\n" + program, timeout=150))
    (ROOT / ".local/nas-parity/runner-before-four-gib.toml").write_bytes(before)
    config.write_bytes(staged.read_bytes())
    marker.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
