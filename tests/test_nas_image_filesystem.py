"""Filesystem equivalence includes permissions and contents, not build clocks."""

import io
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from nas_image_filesystem import differences, inventory  # noqa: E402


def archive(rows):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as stream:
        for name, data, mode, mtime in rows:
            item = tarfile.TarInfo(name)
            item.size, item.mode, item.mtime = len(data), mode, mtime
            stream.addfile(item, io.BytesIO(data))
    output.seek(0)
    return output


def test_order_and_timestamps_do_not_hide_otherwise_identical_filesystems():
    first = inventory(archive([('a', b'one', 0o644, 1), ('b', b'two', 0o755, 2)]))
    second = inventory(archive([('b', b'two', 0o755, 3), ('a', b'one', 0o644, 4)]))
    assert differences(first, second)['same_filesystem']
    assert first['file_bytes_hashed'] == 6 and first['entry_count'] == 2


@pytest.mark.parametrize('data,mode', [(b'changed', 0o644), (b'one', 0o777)])
def test_payload_or_permission_difference_prevents_equivalence(data, mode):
    first = inventory(archive([('a', b'one', 0o644, 1)]))
    second = inventory(archive([('a', data, mode, 1)]))
    result = differences(first, second)
    assert not result['same_filesystem'] and result['changed'] == ['a']


@pytest.mark.parametrize('names', [['../escape'], ['/absolute'], ['a/../b'], ['a', './a']])
def test_uncontained_or_duplicate_archive_names_are_rejected(names):
    with pytest.raises(ValueError):
        inventory(archive([(name, b'x', 0o644, 0) for name in names]))


def test_read_and_entry_budgets_are_enforced():
    with pytest.raises(ValueError):
        inventory(archive([('a', b'too large', 0o644, 0)]), maximum_bytes=2)
    with pytest.raises(ValueError):
        inventory(archive([('a', b'x', 0o644, 0), ('b', b'x', 0o644, 0)]), maximum_entries=1)


def linked_archive(target, *, uid=1000, capability='AQ=='):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as output:
        link = tarfile.TarInfo('bin/tool')
        link.type, link.linkname, link.uid = tarfile.SYMTYPE, target, uid
        link.pax_headers = {'SCHILY.xattr.security.capability': capability}
        output.addfile(link)
    stream.seek(0)
    return stream


@pytest.mark.parametrize('options', [{'target': '/other'}, {'uid': 0}, {'capability': 'Ag=='}])
def test_link_owner_and_capability_changes_remain_visible(options):
    first = inventory(linked_archive('/usr/bin/tool'))
    second = inventory(linked_archive(**({'target': '/usr/bin/tool'} | options)))
    assert differences(first, second)['changed'] == ['bin/tool']
