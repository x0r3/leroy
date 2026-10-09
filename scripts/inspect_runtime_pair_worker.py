"""Verify the actual A/B/A worker against frozen Git and retained original hashes."""

import hashlib
import json
import subprocess

from nas_ssh import ROOT
from prepare_nas_vm import guest

COMMIT = '0ad540dd578033d45e4d0c25d89fbe57b32102a4'
FOLDER = ROOT / 'test-results/nas-parity/followup/frozen-runtime-aba-0ad540dd5780-owned-builder'
BASE = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / COMMIT / 'controlled-groups'
CHECKOUT = ROOT / '.sources/frozen-master/graphato-0ad540dd5780'


def main():
    target = FOLDER / 'worker-original-test-content-proof.json'
    assert not target.exists(), 'Retain the first worker inspection'
    analysis = json.loads((FOLDER / 'analysis.json').read_text())
    ids = {row['browser_worker_image_id'] for row in analysis['samples']}
    assert len(ids) == 1
    identity = ids.pop()
    previous = json.loads((BASE / 'web-soak-cpu-eight-round-2/jenkins-worker-content-proof.json').read_text())
    paths = sorted(previous['files'])
    assert subprocess.check_output(['git', '-C', str(CHECKOUT), 'rev-parse', 'HEAD']).decode().strip() == COMMIT
    assert not subprocess.check_output(['git', '-C', str(CHECKOUT), 'status', '--porcelain'])
    probe = '''const fs=require('node:fs'),crypto=require('node:crypto');
const paths=PATHS,files={},gitBlobs={};
for(const path of paths){const bytes=fs.readFileSync('/build/'+path);
 files[path]=crypto.createHash('sha256').update(bytes).digest('hex');
 gitBlobs[path]=crypto.createHash('sha1').update('blob '+bytes.length+'\\0').update(bytes).digest('hex');}
console.log(JSON.stringify({files,git_blobs:gitBlobs,node_version:process.version,
 playwright_version:require('node:module').createRequire('/build/apps/desktop/package.json')('@playwright/test/package.json').version}));
'''.replace('PATHS', json.dumps(paths))
    program = 'identity=' + repr(identity) + '\nprobe=' + repr(probe) + '\n'
    program += '''import json,subprocess
result=subprocess.run(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL',
 '--security-opt','no-new-privileges:true','--memory','128m','--memory-swap','128m','--pids-limit','32',
 '--entrypoint','node',identity,'-e',probe],text=True,capture_output=True)
assert result.returncode==0,result.stderr[:1800]
value=json.loads(result.stdout)
print(json.dumps(value))
'''
    value = json.loads(guest('sudo python3 -B -', program, timeout=90))
    expected = {}
    for path in paths:
        data = subprocess.check_output(['git', '-C', str(CHECKOUT), 'show', COMMIT + ':' + path])
        expected[path] = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    value.update({
        'image_id': identity, 'frozen_commit': COMMIT,
        'canonical_git_blob_matches': {path: value['git_blobs'][path] == expected[path] for path in paths},
        'retained_original_worker_sha256_matches': {path: value['files'][path] == previous['files'][path] for path in paths},
        'original_worker_evidence': str(BASE.relative_to(ROOT) / 'web-soak-cpu-eight-round-2/jenkins-worker-content-proof.json'),
        'checked_files': len(paths), 'test_source_modified': False,
        'read_only': True, 'network': 'none', 'is_full_worker_file_identity_proof': False,
    })
    assert all(value['canonical_git_blob_matches'].values())
    assert all(value['retained_original_worker_sha256_matches'].values())
    assert value['node_version'] == previous['node_version']
    assert value['playwright_version'] == previous['playwright_version']
    target.write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({'checked_files': len(paths), 'all_original_hashes_match': True,
                      'all_frozen_git_blobs_match': True, 'node': value['node_version'],
                      'playwright': value['playwright_version']}))


if __name__ == '__main__':
    main()
