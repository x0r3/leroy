"""Load a checksum-verified native runtime into the owned diagnostic VM only."""

import argparse
import hashlib
import json
import subprocess

from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT
from nas_target_host_guard import begin as host_begin
from nas_target_host_guard import finish as host_finish
from prepare_nas_vm import guest

EVIDENCE = ROOT / 'test-results/nas-parity/followup/native-browser-observations/web-18'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docker-archive', action='store_true')
    args = parser.parse_args()
    copied = json.loads((EVIDENCE / ('runtime-docker-archive.json' if args.docker_archive else 'runtime-copy.json')).read_text())
    phase = 'runtime-load-docker' if args.docker_archive else 'runtime-load'
    receipt_path = EVIDENCE / ('runtime-import-attempt-docker.json' if args.docker_archive else 'runtime-import-attempt.json')
    assert not receipt_path.exists(), 'Retain the first import attempt for each serialization'
    destination = EVIDENCE / 'runtime-loaded-in-test-vm.json'
    assert not destination.exists(), 'Retain the first verified runtime import'
    archive = (ROOT / copied['archive']).resolve(strict=True)
    assert archive.is_relative_to(ROOT / '.local/native-graphato-runtime')
    assert archive.stat().st_size == copied['archive_size']
    with archive.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == copied['archive_sha256']
    idle()
    host_before = host_begin(EVIDENCE, phase)
    before = begin(EVIDENCE, phase)
    original = json.loads(guest('sudo python3 -B -', '''
import hashlib,json,os,pathlib,shutil,subprocess
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file() and os.cpu_count()==4
assert shutil.disk_usage('/var/lib/docker').free>8*1024**3,'Keep diagnostic import within available guest disk space'
p=pathlib.Path('/opt/graphato/current/manifest.json');m=json.loads(p.read_text())
assert m['commit']=='0ad540dd578033d45e4d0c25d89fbe57b32102a4'
assert m['runtimeImageId']=='sha256:6251c60f499e41e706613f931bf281ce52312b957d5a6a123cf4e27dd3242585'
assert not subprocess.check_output(['docker','ps','-q','--filter','label=io.graphato.e2e.owner'],text=True).strip()
print(json.dumps({'manifest_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'runtime_image_id':m['runtimeImageId']}))
''', timeout=30))
    command = ['ssh', '-i', str(ROOT / '.local/vm/id_ed25519'), '-p', '2225',
               '-o', 'UserKnownHostsFile=' + str(ROOT / '.local/nas-parity/vm/known_hosts'),
               '-o', 'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes',
               '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15',
               'leroy-admin@127.0.0.1', 'sudo docker load']
    with archive.open('rb') as stream:
        result = subprocess.run(command, stdin=stream, capture_output=True, timeout=900)
    import_receipt = {'archive_sha256': copied['archive_sha256'], 'exit_code': result.returncode,
                      'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
                      'stderr_sha256': hashlib.sha256(result.stderr).hexdigest(),
                      'production_modified': False}
    if result.returncode:
        # Docker import messages contain artifact references, never fixture credentials.
        import_receipt['stderr'] = result.stderr.decode(errors='replace')[-4000:]
        import_receipt['qualification'] = finish(EVIDENCE, phase, before)
    receipt_path.write_text(json.dumps(import_receipt, indent=2) + '\n')
    assert result.returncode == 0, 'Runtime archive import failed; retain its receipt before any alternative serialization'
    program = 'reference=' + repr(copied['test_reference']) + '\nexpected=' + repr(copied['rootfs_diff_ids']) + '\noriginal=' + repr(original) + '\n'
    program += '''
import hashlib,json,pathlib,subprocess
image=json.loads(subprocess.check_output(['docker','image','inspect',reference],text=True))[0]
assert image['RootFS']['Layers']==expected
labels=image['Config']['Labels'];assert labels['org.opencontainers.image.revision']=='0ad540dd578033d45e4d0c25d89fbe57b32102a4'
assert not any(value.startswith('GRAPHATO_API_RATE_LIMIT_') for value in image['Config']['Env'])
probe="""import hashlib,json,pathlib,subprocess
p=pathlib.Path('/usr/local/bin/graphato-server')
selected=['/usr/local/bin/node','/usr/local/bin/graphato-entrypoint','/usr/local/bin/graphato-healthcheck','/usr/local/bin/graphato-sandbox-preflight','/usr/lib/x86_64-linux-gnu/libc.so.6','/usr/lib/x86_64-linux-gnu/libssl.so.3','/usr/local/share/graphato-server.rustc-version']
hashes={name:hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest() for name in selected}
packages=subprocess.check_output(['dpkg-query','-W','-f','${Package} ${Version}\\\\n'],text=True).splitlines()
web=pathlib.Path('/usr/share/graphato-web');assets={str(f.relative_to(web)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(web.rglob('*')) if f.is_file() and not f.is_symlink()}
print(json.dumps({'server_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'server_build':json.loads(subprocess.check_output([str(p),'--build-info'],text=True)),'selected_runtime_file_hashes':hashes,'package_versions':packages,'web_asset_hashes':assets}))
"""
def inspect_runtime(identity):
 return json.loads(subprocess.check_output(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','256m','--memory-swap','256m','--pids-limit','32','--entrypoint','python3',identity,'-c',probe],text=True))
value=inspect_runtime(image['Id']);control=inspect_runtime(original['runtime_image_id'])
assert value['server_sha256']=='faab058b0006184428efe434cfaef40028b07b495d9c61b82cf719b9bcb27519'
assert control['server_sha256']=='0f3f4ebb3ea557807528bdb9ee67f6d4cf489f63865d46016ece5ea5a272dfe4'
assert hashlib.sha256(pathlib.Path('/opt/graphato/current/manifest.json').read_bytes()).hexdigest()==original['manifest_sha256']
print(json.dumps({'image_id':image['Id'],'rootfs_diff_ids':expected,'source_commit':labels['org.opencontainers.image.revision'],**value,'control_runtime_observation':control,'selected_runtime_files_equal':value['selected_runtime_file_hashes']==control['selected_runtime_file_hashes'],'package_versions_equal':value['package_versions']==control['package_versions'],'web_assets_equal':value['web_asset_hashes']==control['web_asset_hashes'],'active_release_unchanged':True}))
'''
    observed = json.loads(guest('sudo python3 -B -', program, timeout=60))
    observed.update({'original_registry_manifest_digest': copied['original_registry_manifest_digest'],
                     'config_digest': copied['config_digest'], 'archive_sha256': copied['archive_sha256'],
                     'archive_serialization_changed': True, 'application_and_test_files_modified': False,
                     'production_modified': False,
                     'target_host_qualification': host_finish(EVIDENCE, phase, host_before),
                     'production_measurement_qualification': finish(EVIDENCE, phase, before)})
    destination.write_text(json.dumps(observed, indent=2) + '\n')
    print(json.dumps({'native_runtime_loaded': True, 'image_id': observed['image_id'],
                      'server_sha256': observed['server_sha256'], 'active_release_unchanged': True}), flush=True)


if __name__ == '__main__':
    main()
