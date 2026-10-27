"""Only the documented numeric transport trace may leave protected job logs."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from observe_nas_release_jobs import safe_transport  # noqa: E402


def request():
    return dict(event='request', at_epoch=1.0, wall_seconds=77, thread_cpu_seconds=.01,
                thread_usage_delta=dict(majflt=2, minflt=3, inblock=4, nvcsw=5, nivcsw=6),
                last_event='receive_headers.complete', phases_seconds={'receive_headers': 76}, request_failed=False)


def test_retains_phases_and_thread_resource_evidence():
    assert safe_transport(request()) == request()
    value = dict(event='thread', at_epoch=1, pid=1, thread_id=7,
                 controller_file_mapping_present=True, proxy_environment_present=False)
    assert safe_transport(value) == value


@pytest.mark.parametrize('key,value', [('url', 'http://secret'), ('wall_seconds', float('nan')),
                                     ('last_event', 'secret'), ('phases_seconds', {'authorization': 1}),
                                     ('thread_usage_delta', {'private': 'secret'})])
def test_rejects_private_unknown_or_invalid_fields(key, value):
    item = request()
    item[key] = value
    assert safe_transport(item) is None
