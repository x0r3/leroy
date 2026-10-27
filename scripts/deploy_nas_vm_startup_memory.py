"""Install the bounded snapshot verifier in the owned, stopped NAS test VM only."""

import json

import nas_release_vm as vm
from nas_followup_support import inner, production_jobs
from nas_gitea_target import idle
from nas_ssh import ROOT, upload_file

OLD_SHA = '7343bd1be75da30acc5309e13cf07923d095f61b126f1cf10eb59ba08e29a169'


def main():
    folder = ROOT / 'test-results/nas-parity/followup/vm-startup-memory-20261014'
    assert not folder.exists(), 'Inspect the existing deployment; do not replace its proof'
    idle()
    assert not vm.state()['State']['Running']
    assert inner('inspect', 'jenkins-parity', '--format', '{{.State.Running}}').strip() == 'false'
    before = production_jobs()
    assert not before['active_builds'] and before['older_concurrent_build_history_verified']
    staged = json.loads((vm.LOCAL / 'staged-ssd.json').read_text())
    assert staged['launcher_sha256'] == OLD_SHA
    folder.mkdir()
    (folder / 'staged-ssd-before.json').write_text(json.dumps(staged, indent=2) + '\n')
    source = ROOT / 'infra/vm/launch.py'
    expected = vm.digest(source)
    remote = '/volume1/docker/leroy-nas-parity/vm-startup-memory-20261014'
    vm.remote('import pathlib\np=pathlib.Path(' + repr(remote + '-input') + ')\n'
              "assert not p.exists() and (p.parent/'.leroy-owned').is_file()\np.mkdir(mode=0o700)")
    upload_file(source, remote + '-input/launch.py', vm.CREDENTIALS, timeout=60)
    program = 'ROOT=' + repr(remote) + '\nOLD=' + repr(OLD_SHA) + '\nNEW=' + repr(expected) + '\n' + r'''
import hashlib,json,os,pathlib,shutil,subprocess,time
root=pathlib.Path(ROOT);assert not root.exists() and (root.parent/'.leroy-owned').is_file()
vm=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-release-target-vm'],text=True))[0]
assert not vm['State']['Running']
names=['paperless','sonarr','radarr','sabnzbd','plex','yt-downloader-service','mail-ingest-service']
apps=json.loads(subprocess.check_output(['docker','inspect',*names],text=True))
assert all(c['State']['Running'] and c['State'].get('Health',{}).get('Status') in (None,'healthy') for c in apps)
baseline=pathlib.Path('/overlay/leroy-nas-parity-release-test/0ad540dd5780/baseline')
path=baseline/'launch.py';incoming=pathlib.Path(ROOT+'-input/launch.py')
assert path.resolve(strict=True)==path and not path.is_symlink()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(path)==OLD and sha(incoming)==NEW
identities={p.name:[p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns] for p in baseline.iterdir() if p.name!='launch.py'}
root.mkdir(mode=0o700);shutil.copy2(path,root/'launch-before.py');(root/'launch-before.py').chmod(0o600)
temporary=baseline/'launch.py.startup-memory';assert not temporary.exists()
with temporary.open('xb') as stream:
 stream.write(incoming.read_bytes());stream.flush();os.fsync(stream.fileno())
os.chown(temporary,path.stat().st_uid,path.stat().st_gid);temporary.chmod(0o444)
assert sha(temporary)==NEW;temporary.replace(path)
fd=os.open(baseline,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
assert sha(path)==NEW
assert identities=={p.name:[p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns] for p in baseline.iterdir() if p.name!='launch.py'}
value={'at_epoch':time.time(),'previous_launcher_sha256':OLD,'launcher_sha256':NEW,
 'baseline_and_seed_file_identities_unchanged':True,'vm_started':False,'all_seven_apps_healthy':True,
 'guest_or_fixture_memory_limits_changed':False,'global_host_settings_changed':False}
(root/'proof.json').write_text(json.dumps(value,indent=2)+'\n');(root/'proof.json').chmod(0o600)
print(json.dumps(value))
'''
    proof = json.loads(vm.remote(program, sudo=True, timeout=60))
    assert proof['launcher_sha256'] == expected
    (folder / 'deployment-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    staged['launcher_sha256'] = expected
    path = vm.LOCAL / 'staged-ssd.json'
    temporary = path.with_suffix('.startup-memory.tmp')
    assert not temporary.exists()
    temporary.write_text(json.dumps(staged, indent=2) + '\n')
    temporary.replace(path)
    after = production_jobs()
    assert after['jobs'] == before['jobs'] and not after['active_builds']
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
