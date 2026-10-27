"""Bind current NAS acceptance to the verified pool, retaining legacy guards."""

import hashlib
import json
import re

from nas_ssh import ROOT

LEGACY_JENKINS = '29e75d9173c95db4f448ac038f2593e1f556e7eb2bf49bde68cba911526f3226'
POOL_PROOF = ROOT / 'test-results/nas-parity/followup/engine-storage-20261015-b/deployment-proof.json'


def binding(proof=None):
    if proof is None:
        return {'id': LEGACY_JENKINS, 'image': None, 'volume': 'jenkins-parity-aligned-home'}
    assert proof['qualified_worker_image_config_and_layers_unchanged'] and proof['linux_worker_tests'] == 28
    assert proof['source_service_configuration_unchanged_except_snapshot_image_reference']
    assert proof['existing_named_volumes_reused'] and proof['old_engine_root_retained']
    identity = proof['private_jenkins_container_id']
    image = proof['source_service_rootfs_snapshots']['jenkins-parity']['image']
    assert re.fullmatch('[a-f0-9]{64}', identity) and re.fullmatch('sha256:[a-f0-9]{64}', image)
    return {'id': identity, 'image': image, 'volume': 'jenkins-parity-aligned-home'}


def validate_jenkins(actual, expected):
    assert actual['Id'] == expected['id'] and actual['Name'] == '/jenkins-parity', 'Unexpected private Jenkins identity'
    assert actual['Config']['Labels'].get('io.leroy.nas-parity') == 'true'
    assert expected['image'] is None or actual['Image'] == expected['image'], 'Unexpected private Jenkins image'
    mount, = (m for m in actual['Mounts'] if m['Destination'] == '/var/jenkins_home')
    assert mount['Type'] == 'volume' and mount['Name'] == expected['volume'], 'Unexpected private Jenkins data'
    return {'id': actual['Id'], 'image': actual['Image'], 'volume': mount['Name'], 'running': actual['State']['Running']}


def require_current_jenkins():
    from nas_followup_support import inner

    raw = POOL_PROOF.read_bytes() if POOL_PROOF.exists() else None
    expected = binding(json.loads(raw) if raw is not None else None)
    metadata = validate_jenkins(json.loads(inner('inspect', 'jenkins-parity'))[0], expected)
    metadata['pool_proof_sha256'] = hashlib.sha256(raw).hexdigest() if raw is not None else None
    return metadata
