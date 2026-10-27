"""Compare image filesystem contents independently of build timestamps.

Operator-only streaming inventory. It never extracts or executes image files.
Ownership, modes, links, devices and extended attributes remain significant.
"""

import hashlib
import json
import posixpath
import tarfile
import time


def canonical_path(name):
    if not isinstance(name, str) or '\\' in name or '\x00' in name:
        raise ValueError('Invalid archive path')
    if name.startswith('/') or '..' in name.split('/'):
        raise ValueError('Uncontained archive path')
    return posixpath.normpath(name)


def inventory(stream, *, maximum_bytes=12*1024**3, maximum_entries=200000, maximum_seconds=1200):
    """Hash all exported entries; reject partial, oversized or ambiguous input."""
    entries = {}
    byte_count = 0
    started = time.monotonic()
    with tarfile.open(fileobj=stream, mode='r|') as archive:
        for member in archive:
            if time.monotonic() - started > maximum_seconds:
                raise TimeoutError('Image filesystem inventory deadline reached')
            path = canonical_path(member.name)
            if path in entries or len(entries) >= maximum_entries:
                raise ValueError('Duplicate path or oversized filesystem inventory')
            if member.size < 0 or byte_count + member.size > maximum_bytes:
                raise ValueError('Image filesystem exceeds the read budget')
            byte_count += member.size
            row = {'type': member.type.decode('ascii'), 'uid': member.uid, 'gid': member.gid,
                   'mode': member.mode, 'size': member.size}
            if member.isfile():
                digest = hashlib.sha256()
                source = archive.extractfile(member)
                count = 0
                while data := source.read(1024**2):
                    count += len(data)
                    if time.monotonic() - started > maximum_seconds:
                        raise TimeoutError('Image filesystem inventory deadline reached')
                    digest.update(data)
                if count != member.size:
                    raise ValueError('Incomplete image file')
                row['sha256'] = digest.hexdigest()
            elif member.issym():
                # Absolute symlink targets are legitimate inside Linux images.
                row['link'] = member.linkname
            elif member.islnk():
                row['link'] = canonical_path(member.linkname)
            elif member.ischr() or member.isblk():
                row.update(device_major=member.devmajor, device_minor=member.devminor)
            elif not (member.isdir() or member.isfifo()):
                raise ValueError('Unsupported filesystem entry type')
            attributes = {k: v for k, v in member.pax_headers.items() if k not in {
                'mtime', 'atime', 'ctime', 'path', 'linkpath', 'size', 'uid', 'gid', 'uname', 'gname'}}
            if attributes:
                row['attributes'] = attributes
            entries[path] = row
    canonical = json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()
    return {'entries': entries, 'entry_count': len(entries), 'file_bytes_hashed': byte_count,
            'filesystem_sha256': hashlib.sha256(canonical).hexdigest(),
            'timestamps_ignored': True, 'ownership_modes_links_and_attributes_compared': True}


def differences(first, second):
    """A digest mismatch requires inspection, never an equivalence claim."""
    a, b = first['entries'], second['entries']
    return {'same_filesystem': first['filesystem_sha256'] == second['filesystem_sha256'] and a == b,
            'only_first': sorted(a.keys() - b.keys()), 'only_second': sorted(b.keys() - a.keys()),
            'changed': sorted(k for k in a.keys() & b.keys() if a[k] != b[k]),
            'timestamps_excluded_from_comparison': True}
