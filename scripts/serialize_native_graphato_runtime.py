"""Reserialize verified registry layers as a classic Docker archive, without rebuilding."""

import gzip
import hashlib
import io
import json
import tarfile

from fetch_native_graphato_runtime import CACHE, EVIDENCE
from nas_ssh import ROOT


def main():
    original = json.loads((EVIDENCE / 'runtime-copy.json').read_text())
    attempt = json.loads((EVIDENCE / 'runtime-import-attempt.json').read_text())
    assert attempt['exit_code'] != 0 and attempt['archive_sha256'] == original['archive_sha256']
    destination = EVIDENCE / 'runtime-docker-archive.json'
    assert not destination.exists(), 'Retain the first alternate serialization'
    registry = json.loads((EVIDENCE / 'registry-image-observation.json').read_text())['manifest']
    config = CACHE / 'blobs/sha256' / registry['config']['digest'].removeprefix('sha256:')
    config_data = config.read_bytes()
    assert 'sha256:' + hashlib.sha256(config_data).hexdigest() == original['config_digest']
    files = []
    for layer, diff_id in zip(registry['layers'], original['rootfs_diff_ids'], strict=True):
        blob = CACHE / 'blobs/sha256' / layer['digest'].removeprefix('sha256:')
        with blob.open('rb') as stream:
            assert 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest() == layer['digest']
        target = CACHE / 'uncompressed-layers' / diff_id.removeprefix('sha256:')
        target.parent.mkdir(exist_ok=True)
        if not target.exists():
            with gzip.open(blob, 'rb') as stream, target.open('xb') as output:
                while chunk := stream.read(1024**2):
                    output.write(chunk)
        with target.open('rb') as stream:
            assert 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest() == diff_id
        files.append(target)
    assert sum(path.stat().st_size for path in files) < 8 * 1024**3
    path = CACHE / 'native-runtime.docker.tar'
    names = [item.name + '/layer.tar' for item in files]
    config_name = original['config_digest'].removeprefix('sha256:') + '.json'
    manifest = [{'Config': config_name, 'RepoTags': [original['test_reference']], 'Layers': names}]
    with tarfile.open(path, 'w') as archive:
        for name, data in [(config_name, config_data), ('manifest.json', json.dumps(manifest).encode())]:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(data))
        for file, name in zip(files, names, strict=True):
            archive.add(file, arcname=name, recursive=False)
    with path.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    value = {**original, 'archive': str(path.relative_to(ROOT)),
             'archive_sha256': checksum, 'archive_size': path.stat().st_size,
             'serialization': 'docker-classic', 'original_oci_archive_sha256': original['archive_sha256'],
             'layer_contents_modified': False, 'test_files_modified': False, 'production_modified': False}
    destination.write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({'alternate_archive_verified': True, 'bytes': value['archive_size'],
                      'layer_contents_modified': False}), flush=True)


if __name__ == '__main__':
    main()
