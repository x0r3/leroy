"""Disable test-daemon swapping and use its existing CPU budget symmetrically."""

import hashlib
import json
import tomllib

from nas_followup_support import inner, wait_production_jobs
from nas_gitea_target import idle
from nas_ssh import ROOT, upload_file


def main():
    folder = ROOT / "test-results/nas-parity/followup"
    marker = folder / "antares-safe-budget.json"
    assert not marker.exists(), "No implicit resource reapplication"
    stopped = json.loads((folder / "antares-pressure-browser-termination.json").read_text())
    assert not stopped["production_processes_signalled"] and not stopped["forced"]
    policy = json.loads((folder / "candidates/antares/8607cfd438c7645012bf0482a5da83acb122d6dd/database-storage-corrected.json").read_text())
    assert all(p["helpers_removed"] and p["write_read_verified"] for p in policy["engines"].values())
    before_jobs = wait_production_jobs()
    idle()
    assert json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}")) is False
    config = ROOT / ".local/nas-parity/config/runner.toml"
    before = config.read_bytes()
    text = config.read_text()
    prefix, body = text.split("[profiles.antares]\n", 1)
    section, suffix = body.split("[profiles.antares.environment]", 1)
    assert section.count("cpus = 2\n") == 1
    updated = prefix + "[profiles.antares]\n" + section.replace("cpus = 2\n", "cpus = 6\n") + "[profiles.antares.environment]" + suffix
    expected = tomllib.loads(text)
    expected["profiles"]["antares"]["cpus"] = 6
    assert tomllib.loads(updated) == expected and expected["profiles"]["antares"]["memory"] == "3g"
    staged = ROOT / ".local/nas-parity/runner-antares-safe-budget.toml"
    staged.write_text(updated)
    upload_file(staged, "/volume1/docker/leroy-nas-parity/config/runner-antares-safe-budget.toml", ROOT / ".local/nas-ssh.json")
    program = r'''
import hashlib,json,pathlib,shutil,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
info=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-docker-1'],text=True))[0]
assert info['Id']=='7d029e17dc28b04ec41ac927360062f057c97564227c62e7e01a50a4938b5a00'
assert info['HostConfig']['Memory']==int(4.5*1024**3) and info['HostConfig']['MemorySwap']==6*1024**3
assert info['HostConfig']['NanoCpus']==6_000_000_000
names=subprocess.check_output(['docker','exec',info['Id'],'docker','ps','--format','{{.Names}}'],text=True).splitlines()
assert not any(n.startswith(('antares-','leroy-run-')) for n in names)
path=root/'config/runner.toml';staged=root/'config/runner-antares-safe-budget.toml'
assert hashlib.sha256(path.read_bytes()).hexdigest()==BEFORE and hashlib.sha256(staged.read_bytes()).hexdigest()==AFTER
compose=root/'compose.yaml';original=compose.read_bytes();text=compose.read_text()
assert text.count('memswap_limit: 6144m')==1 and text.count('mem_limit: 4608m')==1
for source,backup in [(path,root/'config/runner-before-safe-budget.toml'),(compose,root/'compose-before-safe-budget.yaml')]:
 assert not backup.exists();shutil.copy2(source,backup)
subprocess.run(['docker','update','--memory-swap','4608m',info['Id']],check=True,capture_output=True,timeout=30)
actual=json.loads(subprocess.check_output(['docker','inspect',info['Id']],text=True))[0]
assert actual['HostConfig']['MemorySwap']==actual['HostConfig']['Memory']==int(4.5*1024**3)
compose.write_text(text.replace('memswap_limit: 6144m','memswap_limit: 4608m'))
shutil.copyfile(staged,path);path.chmod(0o644)
subprocess.run(['docker','compose','up','-d','--no-deps','--force-recreate','runner'],cwd=root,check=True,capture_output=True,timeout=120)
cgroup=pathlib.Path('/sys/fs/cgroup/system.slice/docker-'+info['Id']+'.scope')
assert (cgroup/'memory.swap.max').read_text().strip()=='0'
print(json.dumps({'owned_daemon':info['Id'],'memory_bytes':actual['HostConfig']['Memory'],
 'memory_swap_bytes':actual['HostConfig']['MemorySwap'],'cgroup_swap_max':0,
 'existing_swap_bytes':int((cgroup/'memory.swap.current').read_text()),'cpus':6,
 'runner_before_sha256':BEFORE,'runner_after_sha256':AFTER,
 'compose_before_sha256':hashlib.sha256(original).hexdigest(),'compose_after_sha256':hashlib.sha256(compose.read_bytes()).hexdigest(),
 'daemon_restarted':False,'other_profiles_unchanged':True,'production_modified':False,
 'original_test_assertions_and_deadlines_unchanged':True,'full_ci_acceptance':False}))
'''
    old_hash = hashlib.sha256(before).hexdigest()
    new_hash = hashlib.sha256(staged.read_bytes()).hexdigest()
    # cgroup reading requires NAS administration, not access to production containers.
    from nas_ssh import run_script

    result = run_script("python3 - <<'PY'\nBEFORE=" + repr(old_hash) + "\nAFTER=" + repr(new_hash) + "\n" + program + "\nPY\n",
                        ROOT / ".local/nas-ssh.json", sudo=True, timeout=180)
    assert result.returncode == 0, result.stderr[-1200:]
    record = json.loads(result.stdout)
    config.write_bytes(staged.read_bytes())
    compose = ROOT / "infra/nas/compose.yaml"
    text = compose.read_text()
    assert text.count("memswap_limit: 6144m") == 1
    compose.write_text(text.replace("memswap_limit: 6144m", "memswap_limit: 4608m"))
    after_jobs = wait_production_jobs()
    record["production_jobs_unchanged"] = before_jobs["jobs"] == after_jobs["jobs"]
    assert record["production_jobs_unchanged"]
    marker.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
