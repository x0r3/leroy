"""Read selected metadata from stopped release disks, without mounting or booting.

Dissect is an optional operator tool staged separately, never a Leroy runtime
dependency. The caller supplies an already opened, read-only root filesystem.
Only hashes of commands, environment and arbitrary log contents leave the probe.
"""

import hashlib
import json
import re
import struct
from datetime import datetime, timezone


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read_file(fs, path, maximum=4 * 1024**2):
    node = fs.get(path)
    if node.size > maximum:
        raise ValueError('Forensic file exceeds the bounded read size')
    with node.open() as stream:
        data = stream.read(maximum + 1)
    if len(data) != node.size:
        raise ValueError('Incomplete forensic file')
    return data


def image_metadata(fs, identity):
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', identity):
        raise ValueError('Expected an immutable image config digest')
    chain = []
    current = identity
    for _ in range(5):
        digest = current.removeprefix('sha256:')
        paths = (
            '/var/lib/containerd/io.containerd.content.v1.content/blobs/sha256/' + digest,
            '/var/lib/docker/image/overlay2/imagedb/content/sha256/' + digest,
        )
        for path in paths:
            try:
                raw = read_file(fs, path)
                break
            except FileNotFoundError:
                continue
        else:
            raise FileNotFoundError('Recorded worker image metadata is absent from retained disk')
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('Image metadata does not match its immutable digest')
        chain.append(current)
        config = json.loads(raw)
        if 'manifests' in config:
            candidates = [row for row in config['manifests']
                          if row.get('platform', {}).get('os') == 'linux'
                          and row.get('platform', {}).get('architecture') == 'amd64']
            if len(candidates) != 1:
                raise ValueError('Expected exactly one Linux amd64 worker manifest')
            current = candidates[0]['digest']
        elif 'config' in config and isinstance(config['config'], dict) and 'digest' in config['config']:
            current = config['config']['digest']
        else:
            break
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', current) or current in chain:
            raise ValueError('Invalid or cyclic image descriptor')
    else:
        raise ValueError('Too many image descriptor levels')
    if 'rootfs' in config:
        rootfs = config['rootfs']
        layers = rootfs['diff_ids']
        if rootfs['type'] != 'layers' or not layers or not all(
                re.fullmatch(r'sha256:[a-f0-9]{64}', value) for value in layers):
            raise ValueError('Invalid image filesystem layer identity')
        return {
            'image_id': identity, 'image_identity_chain': chain,
            'config_digest_verified': True, 'created': config.get('created'),
            'architecture': config['architecture'], 'os': config['os'], 'rootfs': rootfs,
            'execution_config_sha256': canonical_sha(config.get('config')),
            'config_without_created_and_history_sha256': canonical_sha({
                key: value for key, value in config.items() if key not in {'created', 'history'}}),
            'history': [{'created': row.get('created'), 'empty_layer': bool(row.get('empty_layer')),
                         'instruction_sha256': canonical_sha(row.get('created_by'))}
                        for row in config.get('history', [])],
            'raw_commands_or_environment_retained': False,
        }
    raise ValueError('Image descriptor did not resolve to a filesystem config')


def baseline_containers(fs):
    result = []
    for node in fs.get('/var/lib/docker/containers').iterdir():
        if not re.fullmatch('[a-f0-9]{64}', node.filename):
            continue
        root = '/var/lib/docker/containers/' + node.filename
        config = json.loads(read_file(fs, root + '/config.v2.json'))
        labels = config.get('Config', {}).get('Labels', {})
        if labels.get('com.docker.compose.project') != 'graphato-prod':
            continue
        host = json.loads(read_file(fs, root + '/hostconfig.json'))
        state = config['State']
        result.append({
            'id': node.filename, 'service': labels['com.docker.compose.service'],
            'restart_count': config.get('RestartCount'),
            'state': {key: state.get(key) for key in
                      ('Running', 'OOMKilled', 'ExitCode', 'StartedAt', 'FinishedAt')},
            'limits': {key: host.get(key) for key in ('Memory', 'MemorySwap', 'NanoCpus')},
            'stop_timeout': config.get('Config', {}).get('StopTimeout'),
            'pid_namespace': host.get('PidMode'),
        })
    return sorted(result, key=lambda row: row['service'])


def compare_images(first, second):
    """Timestamp/config identity differences alone do not certify equal contents."""
    left, right = first['rootfs']['diff_ids'], second['rootfs']['diff_ids']
    same_layers = left == right
    same_config = first['execution_config_sha256'] == second['execution_config_sha256']
    return {
        'same_image_id': first['image_id'] == second['image_id'],
        'same_platform': (first['os'], first['architecture']) == (second['os'], second['architecture']),
        'same_ordered_rootfs_diff_ids': same_layers,
        'same_execution_config': same_config,
        'layer_counts': [len(left), len(right)],
        'different_layer_indices': [i for i in range(max(len(left), len(right)))
                                    if left[i:i + 1] != right[i:i + 1]],
        'same_declared_filesystem_content_and_execution_config': same_layers and same_config,
        'all_layer_payloads_rehashed': False,
        'missing_original_ci_archives_replaced': False,
    }


def local_log_entries(raw):
    """Decode Docker local log framing and selected protobuf scalar fields.

    Format: moby/moby daemon/logger/local/read.go and
    daemon/logger/internal/logdriver/entry.proto. No log data is executed.
    """
    def varint(data, offset):
        value = 0
        for shift in range(0, 70, 7):
            if offset >= len(data):
                raise ValueError('Truncated protobuf varint')
            byte = data[offset]
            offset += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value, offset
        raise ValueError('Oversized protobuf varint')

    offset = 0
    while offset < len(raw):
        if offset + 8 > len(raw):
            raise ValueError('Truncated Docker log frame')
        size = struct.unpack_from('>I', raw, offset)[0]
        end = offset + size + 4
        if size > 1_000_000 or end + 4 > len(raw):
            raise ValueError('Invalid Docker log frame size')
        if struct.unpack_from('>I', raw, end)[0] != size:
            raise ValueError('Docker log frame footer mismatch')
        body, fields, position = raw[offset + 4:end], {}, 0
        while position < len(body):
            tag, position = varint(body, position)
            if tag >> 3 == 0:
                raise ValueError('Invalid protobuf field')
            wire = tag & 7
            if wire == 0:
                value, position = varint(body, position)
            elif wire in (1, 2, 5):
                if wire == 2:
                    length, position = varint(body, position)
                else:
                    length = 8 if wire == 1 else 4
                value = body[position:position + length]
                if len(value) != length:
                    raise ValueError('Truncated protobuf field')
                position += length
            else:
                raise ValueError('Unsupported protobuf wire type')
            if (tag >> 3, wire) in {(1, 2), (2, 0), (3, 2)}:
                fields[tag >> 3] = value
        if not {1, 2} <= fields.keys():
            raise ValueError('Incomplete Docker log message')
        yield {'source': fields[1].decode(), 'time_nano': fields[2],
               'line': fields.get(3, b'').decode(errors='replace')}
        offset = end + 4


def ownership_log_proof(raw):
    """Retain exact known ownership messages, never arbitrary application logs."""
    known = {
        'runtime error: The PostgreSQL runtime ownership lease was lost; the server stopped and must be restarted': 'lease_lost',
        'runtime error: The execution worker exited uncleanly; persistent runtime ownership was retained and requires explicit recovery': 'unclean_worker',
        'runtime error: Previous runtime ownership is unresolved. Stop every previous execution host, then run --recover-runtime-ownership --acknowledge-all-previous-owners-stopped': 'unresolved_owner',
    }
    first, counts = {}, {}
    for row in local_log_entries(raw):
        kind = known.get(row['line'])
        if kind is None:
            continue
        counts[kind] = counts.get(kind, 0) + 1
        first.setdefault(kind, {
            'at': datetime.fromtimestamp(row['time_nano'] / 1e9, timezone.utc).isoformat(),
            'time_nano': row['time_nano'], 'message': row['line'],
        })
    return {'log_sha256': hashlib.sha256(raw).hexdigest(), 'first_events': first, 'counts': counts,
            'underlying_database_error_or_timeout_distinguished': False,
            'arbitrary_log_lines_retained': False, 'original_ci_archive': False}
