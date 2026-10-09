"""Copy the verified original runtime from the NAS registry for isolated diagnosis."""

import gzip
import hashlib
import io
import json
import re
import shlex
import shutil
import subprocess
import tarfile
import threading

from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, connection

COMMIT = '0ad540dd578033d45e4d0c25d89fbe57b32102a4'
EVIDENCE = ROOT / 'test-results/nas-parity/followup/native-browser-observations/web-18'
CACHE = ROOT / '.local/native-graphato-runtime' / COMMIT


def fetch(kind, digest, size=None):
    assert kind in {'manifests', 'blobs'} and re.fullmatch('sha256:[a-f0-9]{64}', digest)
    path = CACHE / 'blobs/sha256' / digest.removeprefix('sha256:')
    if path.exists():
        with path.open('rb') as stream:
            assert 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest() == digest
        assert size is None or path.stat().st_size == size
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix('.partial')
    program = "import sys,urllib.request\n"
    program += "with urllib.request.urlopen(" + repr('http://127.0.0.1:5005/v2/graphato/server/' + kind + '/' + digest) + ",timeout=30) as response:\n"
    program += " while chunk:=response.read(1024**2):sys.stdout.buffer.write(chunk)\n"
    settings, args, env = connection(ROOT / '.local/nas-ssh.json')
    command = 'python3 -c ' + shlex.quote(program)
    process = subprocess.Popen([*args, settings['username'] + '@' + settings['host'], command],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    watchdog = threading.Timer(900, process.terminate)
    watchdog.daemon = True
    watchdog.start()
    received = 0
    checksum = hashlib.sha256()
    try:
        with partial.open('wb') as stream:
            while chunk := process.stdout.read(1024**2):
                received += len(chunk)
                assert received <= (size if size is not None else 1024**2)
                stream.write(chunk)
                checksum.update(chunk)
        assert process.wait(timeout=30) == 0, 'Bounded read-only registry transfer failed'
        assert 'sha256:' + checksum.hexdigest() == digest
        assert size is None or received == size
        partial.replace(path)
        print(json.dumps({'verified_registry_blob': digest, 'bytes': received}), flush=True)
        return path
    finally:
        watchdog.cancel()
        process.stdout.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=30)


def main():
    metadata = json.loads((EVIDENCE / 'registry-image-observation.json').read_text())
    original = json.loads((EVIDENCE / 'ci-23-manifest-observation.json').read_text())['manifest']
    assert metadata['found'] and original['commit'] == COMMIT
    digest = original['imageDigest']
    assert metadata['image_digest'] == digest
    manifest = metadata['manifest']
    assert manifest['config']['digest'] == 'sha256:' + original['files']['image-config.json']
    assert len(manifest['layers']) == 20
    total = sum(layer['size'] for layer in manifest['layers'])
    assert total < 2 * 1024**3 and shutil.disk_usage(ROOT).free > total * 3 + 2 * 1024**3
    destination = EVIDENCE / 'runtime-copy.json'
    assert not destination.exists(), 'Retain the first verified artifact copy'
    before = begin(EVIDENCE, 'runtime-copy')
    paths = [fetch('manifests', digest)]
    paths.append(fetch('blobs', manifest['config']['digest'], manifest['config']['size']))
    config = json.loads(paths[-1].read_text())
    assert config['config']['Labels']['org.opencontainers.image.revision'] == COMMIT
    diff_ids = config['rootfs']['diff_ids']
    assert len(diff_ids) == len(manifest['layers'])
    for layer, diff_id in zip(manifest['layers'], diff_ids, strict=True):
        path = fetch('blobs', layer['digest'], layer['size'])
        with gzip.open(path, 'rb') as stream:
            assert 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest() == diff_id
        paths.append(path)
    archive_path = CACHE / 'native-runtime.oci.tar'
    reference = 'leroy-diagnostic/graphato-native-runtime:' + COMMIT[:12]
    index = {'schemaVersion': 2, 'manifests': [{'mediaType': manifest['mediaType'], 'digest': digest,
              'size': paths[0].stat().st_size, 'platform': {'architecture': 'amd64', 'os': 'linux'},
              'annotations': {'org.opencontainers.image.ref.name': reference}}]}
    with tarfile.open(archive_path, 'w') as archive:
        for name, value in [('oci-layout', {'imageLayoutVersion': '1.0.0'}), ('index.json', index)]:
            data = json.dumps(value, separators=(',', ':')).encode()
            item = tarfile.TarInfo(name)
            item.size = len(data)
            item.mode = 0o644
            archive.addfile(item, io.BytesIO(data))
        for path in paths:
            archive.add(path, arcname=path.relative_to(CACHE).as_posix(), recursive=False)
    with archive_path.open('rb') as stream:
        archive_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    qualification = finish(EVIDENCE, 'runtime-copy', before)
    value = {'commit': COMMIT, 'original_ci_build': 23, 'original_web_build': 18,
             'original_registry_manifest_digest': digest, 'config_digest': manifest['config']['digest'],
             'rootfs_diff_ids': diff_ids, 'original_build': original['build'],
             'archive': str(archive_path.relative_to(ROOT)), 'archive_sha256': archive_sha,
             'archive_size': archive_path.stat().st_size, 'test_reference': reference,
             'all_registry_blobs_and_uncompressed_layers_verified': True,
             'archive_serialization_changed': True, 'application_and_test_files_modified': False,
             'production_modified': False, 'production_measurement_qualification': qualification}
    destination.write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({'original_runtime_copied': True, 'bytes': value['archive_size'],
                      'application_and_test_files_modified': False}), flush=True)


if __name__ == '__main__':
    main()
