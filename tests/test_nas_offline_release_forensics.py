"""Offline evidence rejects corruption, ambiguous images and false equivalence."""

import hashlib
import io
import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nas_offline_release_forensics as reader  # noqa: E402


class Files:
    def __init__(self):
        self.files = {}

    def put(self, value):
        raw = json.dumps(value).encode()
        digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
        self.files[digest.removeprefix('sha256:')] = raw
        return digest

    def get(self, path):
        try:
            raw = self.files[path.rsplit('/', 1)[-1]]
        except KeyError:
            raise FileNotFoundError(path) from None
        return type('Node', (), {'size': len(raw), 'open': lambda _: io.BytesIO(raw)})()


def config():
    return {'architecture': 'amd64', 'os': 'linux', 'created': '2026-10-13T00:00:00Z',
            'rootfs': {'type': 'layers', 'diff_ids': ['sha256:' + 'a' * 64]},
            'config': {'Env': ['PRIVATE_TOKEN=never-print-this']},
            'history': [{'created_by': 'RUN private-build-argument', 'empty_layer': False}]}


def test_resolves_index_manifest_and_config_with_verified_hashes():
    files = Files()
    identity = files.put(config())
    manifest = files.put({'config': {'digest': identity}})
    index = files.put({'manifests': [
        {'platform': {'os': 'unknown', 'architecture': 'unknown'}, 'digest': 'sha256:' + 'f' * 64},
        {'platform': {'os': 'linux', 'architecture': 'amd64'}, 'digest': manifest}]})
    value = reader.image_metadata(files, index)
    assert value['image_identity_chain'] == [index, manifest, identity]
    assert value['config_digest_verified']
    assert 'never-print-this' not in json.dumps(value)
    assert 'private-build-argument' not in json.dumps(value)


def test_corrupted_image_blob_is_rejected():
    files = Files()
    identity = files.put(config())
    files.files[identity.removeprefix('sha256:')] += b' '
    with pytest.raises(ValueError, match='immutable digest'):
        reader.image_metadata(files, identity)


def test_ambiguous_platform_is_not_guessed():
    files = Files()
    identity = files.put({'manifests': [
        {'platform': {'os': 'linux', 'architecture': 'amd64'}, 'digest': 'sha256:' + 'a' * 64}]*2})
    with pytest.raises(ValueError, match='exactly one'):
        reader.image_metadata(files, identity)


def test_different_layers_cannot_be_explained_away_as_creation_time():
    files = Files()
    first = reader.image_metadata(files, files.put(config()))
    other = config()
    other['rootfs']['diff_ids'] = ['sha256:' + 'b' * 64]
    second = reader.image_metadata(files, files.put(other))
    result = reader.compare_images(first, second)
    assert result['same_execution_config']
    assert result['different_layer_indices'] == [0]
    assert not result['same_declared_filesystem_content_and_execution_config']


def test_equal_layer_declarations_do_not_claim_payloads_rehashed():
    files = Files()
    first = reader.image_metadata(files, files.put(config()))
    other = config()
    other['created'] = '2026-10-14T00:00:00Z'
    second = reader.image_metadata(files, files.put(other))
    value = reader.compare_images(first, second)
    assert not value['same_image_id']
    assert value['same_declared_filesystem_content_and_execution_config']
    assert not value['all_layer_payloads_rehashed']


def test_oversized_metadata_is_not_read():
    class Huge:
        size = 5 * 1024**2

        def open(self):
            pytest.fail('Oversized data must not be opened')

    with pytest.raises(ValueError, match='bounded'):
        reader.read_file(type('FS', (), {'get': lambda _, path: Huge()})(), '/large')


def varint(value):
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    return bytes(out + bytes([value]))


def frame(line, at=1791922434363132201):
    line = line.encode()
    body = b'\x0a\x06stderr\x10' + varint(at) + b'\x1a' + varint(len(line)) + line
    length = struct.pack('>I', len(body))
    return length + body + length


def test_lease_loss_precedes_restart_latch_and_unrelated_logs_are_redacted():
    lost = 'runtime error: The PostgreSQL runtime ownership lease was lost; the server stopped and must be restarted'
    raw = frame('private-provider-token') + frame(lost) + frame(lost, at=1791922435363132201)
    value = reader.ownership_log_proof(raw)
    assert value['counts'] == {'lease_lost': 2}
    assert value['first_events']['lease_lost']['time_nano'] == 1791922434363132201
    assert 'private-provider-token' not in json.dumps(value)
    assert not value['underlying_database_error_or_timeout_distinguished']


def test_proto3_empty_line_can_be_omitted():
    body = b'\x0a\x06stderr\x10' + varint(1791922434363132201)
    length = struct.pack('>I', len(body))
    assert list(reader.local_log_entries(length + body + length))[0]['line'] == ''


@pytest.mark.parametrize('raw', [b'\x00', frame('x')[:-1], frame('x')[:-4] + b'\x00\x00\x00\x00'])
def test_corrupt_log_frames_are_rejected(raw):
    with pytest.raises(ValueError):
        list(reader.local_log_entries(raw))
