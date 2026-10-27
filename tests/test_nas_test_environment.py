"""Changing the isolated pool must retain identity, image and data guards."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from nas_test_environment import binding, validate_jenkins  # noqa: E402


def proof():
    return {'qualified_worker_image_config_and_layers_unchanged': True, 'linux_worker_tests': 28,
            'source_service_configuration_unchanged_except_snapshot_image_reference': True,
            'existing_named_volumes_reused': True, 'old_engine_root_retained': True,
            'private_jenkins_container_id': 'a' * 64,
            'source_service_rootfs_snapshots': {'jenkins-parity': {'image': 'sha256:' + 'b' * 64}}}


def container():
    return {'Id': 'a' * 64, 'Name': '/jenkins-parity', 'Image': 'sha256:' + 'b' * 64,
            'Config': {'Labels': {'io.leroy.nas-parity': 'true'}}, 'State': {'Running': False},
            'Mounts': [{'Destination': '/var/jenkins_home', 'Type': 'volume', 'Name': 'jenkins-parity-aligned-home'}]}


def test_verified_pool_binding_accepts_only_the_proven_replacement():
    assert validate_jenkins(container(), binding(proof()))['id'] == 'a' * 64


@pytest.mark.parametrize('field,value', [('Id', 'c' * 64), ('Name', '/jenkins'), ('Image', 'sha256:' + 'c' * 64)])
def test_name_alone_never_substitutes_for_identity_or_image(field, value):
    actual = container()
    actual[field] = value
    with pytest.raises(AssertionError):
        validate_jenkins(actual, binding(proof()))


def test_rejects_unowned_container_or_changed_data_volume():
    for mutate in (lambda c: c['Config']['Labels'].clear(), lambda c: c['Mounts'][0].update(Name='production-home')):
        actual = container()
        mutate(actual)
        with pytest.raises(AssertionError):
            validate_jenkins(actual, binding(proof()))


def test_incomplete_pool_proof_cannot_replace_legacy_identity():
    bad = copy.deepcopy(proof())
    bad['linux_worker_tests'] = 27
    with pytest.raises(AssertionError):
        binding(bad)
    with pytest.raises(AssertionError):
        validate_jenkins(container(), binding())
