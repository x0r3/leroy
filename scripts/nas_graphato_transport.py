"""Bind fresh acceptance to the Linux-qualified upstream Graphato SSH adapter."""
import json

import nas_release_vm as vm

FOLDER = vm.ROOT / 'test-results/nas-parity/followup/graphato-upstream-transport-20261016-b'


def binding():
    qualified = json.loads((FOLDER / 'qualification-proof.json').read_text())
    deployed = json.loads((FOLDER / 'deployment-proof.json').read_text())
    assert qualified['all_passed'] is True and qualified['linux_tests'] == 37
    assert qualified['failures_or_skips'] == 0 and qualified['frozen_graphato_commit'] == vm.COMMIT
    assert qualified['actions_sha256'] == vm.digest(vm.ROOT / 'src/leroy/actions.py')
    assert qualified['worker_sha256'] == vm.digest(vm.ROOT / 'src/leroy/worker.py')
    assert qualified['lease_trace_sha256'] == vm.digest(vm.ROOT / 'src/leroy/lease_trace.py')
    assert qualified['original_postdeploy_success_and_connection_failure_recovery_tested'] is True
    assert qualified['only_actions_layer_added'] is qualified['image_configuration_unchanged'] is True
    assert qualified['worker_and_lease_trace_unchanged'] is True
    assert qualified['vm_started'] is qualified['real_ssh_requests_sent'] is qualified['production_modified'] is False
    assert qualified['frozen_scripts_sha256'] == {
        'ci.py': 'dbd54cf7cabd5f2bd7798f0d8c6fdc23d1668e65c55738893ab8c343ee728204',
        'deploy-remote.py': '2f989748a2355248ad2d8e5e76778fdd26e16ccb834855f2b4e480fb6a46827a'}
    assert deployed['worker_image'] == qualified['candidate_image']
    assert deployed['previous_worker_image'] == qualified['previous_worker_image']
    assert deployed['actions_sha256'] == qualified['actions_sha256']
    assert deployed['exact_linux_qualified_image_deployed'] is True
    assert deployed['changed_profile_fields'] == ['graphato.image']
    assert deployed['controller_postgres_and_daemon_restarted'] is False
    assert deployed['graphato_source_or_tests_changed'] is deployed['production_modified'] is False
    assert deployed['local_cutoff_seconds'] == 45 and deployed['server_lease_seconds'] == 90
    return {'worker_image': deployed['worker_image'], 'actions_sha256': qualified['actions_sha256'],
            'qualification_sha256': vm.digest(FOLDER / 'qualification-proof.json'),
            'deployment_sha256': vm.digest(FOLDER / 'deployment-proof.json'),
            'original_workload_passed': False}
