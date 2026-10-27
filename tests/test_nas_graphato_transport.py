"""The fresh comparison must use precisely the qualified Graphato adapter."""
import copy
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def transport(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    module = importlib.import_module('nas_graphato_transport')
    monkeypatch.setattr(module, 'FOLDER', tmp_path)
    monkeypatch.setattr(module.vm, 'digest', lambda p: Path(p).name)
    q = {'all_passed': True, 'linux_tests': 37, 'failures_or_skips': 0,
         'frozen_graphato_commit': module.vm.COMMIT, 'actions_sha256': 'actions.py',
         'worker_sha256': 'worker.py', 'lease_trace_sha256': 'lease_trace.py',
         'original_postdeploy_success_and_connection_failure_recovery_tested': True,
         'only_actions_layer_added': True, 'image_configuration_unchanged': True,
         'worker_and_lease_trace_unchanged': True, 'vm_started': False,
         'real_ssh_requests_sent': False, 'production_modified': False,
         'frozen_scripts_sha256': {
             'ci.py': 'dbd54cf7cabd5f2bd7798f0d8c6fdc23d1668e65c55738893ab8c343ee728204',
             'deploy-remote.py': '2f989748a2355248ad2d8e5e76778fdd26e16ccb834855f2b4e480fb6a46827a'},
         'candidate_image': 'qualified-image', 'previous_worker_image': 'previous-image'}
    d = {'worker_image': 'qualified-image', 'previous_worker_image': 'previous-image',
         'actions_sha256': 'actions.py', 'exact_linux_qualified_image_deployed': True,
         'changed_profile_fields': ['graphato.image'], 'controller_postgres_and_daemon_restarted': False,
         'graphato_source_or_tests_changed': False, 'production_modified': False,
         'local_cutoff_seconds': 45, 'server_lease_seconds': 90}
    return module, tmp_path, q, d


@pytest.mark.parametrize('target,change', [
    ('q', {'all_passed': False}), ('q', {'actions_sha256': 'unqualified'}),
    ('q', {'frozen_graphato_commit': 'another-commit'}), ('q', {'failures_or_skips': 1}),
    ('d', {'worker_image': 'another-image'}), ('d', {'graphato_source_or_tests_changed': True}),
    ('d', {'local_cutoff_seconds': 60}), ('d', {'changed_profile_fields': ['graphato.image', 'capacity']}),
])
def test_deployment_cannot_qualify_other_code_images_sources_or_limits(transport, target, change):
    module, folder, q, d = transport
    for p, value in [('qualification-proof.json', q), ('deployment-proof.json', d)]:
        (folder / p).write_text(json.dumps(value))
    assert module.binding()['original_workload_passed'] is False
    altered = copy.deepcopy(q if target == 'q' else d)
    altered.update(change)
    path = folder / ('qualification-proof.json' if target == 'q' else 'deployment-proof.json')
    path.write_text(json.dumps(altered))
    with pytest.raises(AssertionError):
        module.binding()
