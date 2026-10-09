"""Record the aborted probe and reserve NAS headroom for its controller/services."""

import hashlib
import json
import tomllib
from datetime import datetime, timezone

from nas_followup_support import inner, production_jobs
from nas_ssh import ROOT, run_script, upload_file
from probe_nas_antares_browsers import resource_snapshot


def main():
    commit = "58da3ef5d112f58bc0a3d1cbd75179eb71d421c1"
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / commit
    marker = folder / "focused-browsers-capture-dialog-safe-recovery.json"
    assert not marker.exists(), "No implicit recovery reapplication"
    original = json.loads((folder / "focused-browsers-capture-dialog-safe.json").read_text())
    terminated = json.loads((folder / "focused-browsers-capture-dialog-safe-termination.json").read_text())
    assert original["timed_out"] and not original["passed"]
    assert not terminated["production_processes_signalled"] and not terminated["forced"]
    index = json.loads((folder / "browser-failures-capture-dialog-safe/index.json").read_text())
    assert index and all(row["copied"] for row in index)
    from collect_nas_antares_browser_failures import artifact_path
    for row in index:
        path = artifact_path(folder / "browser-failures-capture-dialog-safe", row["name"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
    probe = "antares-browser-probe-58da3ef5d112-capture-dialog-safe"
    info = json.loads(inner("inspect", probe, timeout=60))[0]
    assert info["Id"] == "5d395616eb80cf9bc76c60930966c4a3a84386ece96a362841187e243cf9301f"
    assert info["Config"]["Labels"]["io.leroy.nas-parity"] == "true" and not info["State"]["Running"]
    jobs = production_jobs()
    assert jobs["jobs"] == original["production_jobs_before"]["jobs"]
    inner("rm", probe, timeout=60)
    names = inner("ps", "--format", "{{.Names}}").splitlines()
    assert not any(n.startswith(("antares-", "leroy-")) for n in names)
    config = ROOT / ".local/nas-parity/config/runner.toml"
    before = config.read_bytes()
    text = config.read_text()
    prefix, rest = text.split("[profiles.antares]", 1)
    _, suffix = rest.split("[profiles.image-builds]", 1)
    updated = prefix + "[profiles.image-builds]" + suffix
    expected = tomllib.loads(text)
    assert expected.pop("profiles")["antares"]["memory"] == "4g"
    expected = tomllib.loads(text)
    expected["profiles"].pop("antares")
    assert tomllib.loads(updated) == expected
    staged = ROOT / ".local/nas-parity/runner-without-heavy-antares.toml"
    staged.write_text(updated)
    upload_file(staged, "/volume1/docker/leroy-nas-parity/config/runner-without-heavy-antares.toml", ROOT / ".local/nas-ssh.json")
    program = r'''
import hashlib,json,pathlib,shutil,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
info=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-docker-1'],text=True,timeout=20))[0]
assert info['Id']=='7d029e17dc28b04ec41ac927360062f057c97564227c62e7e01a50a4938b5a00'
assert info['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
assert info['HostConfig']['Memory']==info['HostConfig']['MemorySwap']==int(4.5*1024**3)
cgroup=pathlib.Path('/sys/fs/cgroup/system.slice/docker-'+info['Id']+'.scope')
assert int((cgroup/'memory.current').read_text())<2*1024**3
names=subprocess.check_output(['docker','exec',info['Id'],'docker','ps','--format','{{.Names}}'],text=True,timeout=30).splitlines()
assert not any(n.startswith(('antares-','leroy-')) for n in names)
path=root/'config/runner.toml';staged=root/'config/runner-without-heavy-antares.toml'
assert hashlib.sha256(path.read_bytes()).hexdigest()==BEFORE
assert hashlib.sha256(staged.read_bytes()).hexdigest()==AFTER
compose=root/'compose.yaml';text=compose.read_text();assert text.count('4608m')==2
for path_to_backup in [path,compose]:
 backup=path_to_backup.with_name(path_to_backup.name+'.before-linux-pool')
 assert not backup.exists();shutil.copy2(path_to_backup,backup)
subprocess.run(['docker','update','--memory','3g','--memory-swap','3g',info['Id']],check=True,capture_output=True,timeout=30)
compose.write_text(text.replace('4608m','3072m'))
shutil.copyfile(staged,path);path.chmod(0o644)
subprocess.run(['docker','compose','up','-d','--no-deps','--force-recreate','runner'],cwd=root,check=True,capture_output=True,timeout=120)
actual=json.loads(subprocess.check_output(['docker','inspect',info['Id']],text=True,timeout=20))[0]
assert actual['HostConfig']['Memory']==actual['HostConfig']['MemorySwap']==3*1024**3
assert (cgroup/'memory.swap.max').read_text().strip()=='0'
print(json.dumps({'parent_memory_bytes':3*1024**3,'parent_memory_swap_bytes':3*1024**3,
 'runner_before_sha256':BEFORE,'runner_after_sha256':AFTER,'heavy_antares_profile_removed_from_nas_worker':True,
 'other_profiles_unchanged':True,'daemon_restarted':False,'production_modified':False}))
'''
    result = run_script("python3 - <<'PY'\nBEFORE=" + repr(hashlib.sha256(before).hexdigest())
                        + "\nAFTER=" + repr(hashlib.sha256(staged.read_bytes()).hexdigest()) + "\n" + program + "\nPY\n",
                        ROOT / ".local/nas-ssh.json", sudo=True, timeout=180)
    assert result.returncode == 0, result.stderr[-1500:]
    record = json.loads(result.stdout)
    config.write_bytes(staged.read_bytes())
    compose = ROOT / "infra/nas/compose.yaml"
    assert compose.read_text().count("4608m") == 2
    compose.write_text(compose.read_text().replace("4608m", "3072m"))
    record.update(at=datetime.now(timezone.utc).isoformat(), diagnostic_passed=False,
                  aborted_for_host_pressure=True, complete_browser_summary=False,
                  retained_failure_files=len(index), helpers_removed=True,
                  production_jobs_unchanged=production_jobs()["jobs"] == jobs["jobs"],
                  resources_after=resource_snapshot(), full_ci_acceptance=False, production_cutover=False)
    assert record["production_jobs_unchanged"]
    marker.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
