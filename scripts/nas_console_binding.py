"""Bind the corrected controller to Linux and real-worker backpressure evidence."""

import json

import nas_release_vm as vm


def binding(*, current=False):
    folder = vm.ROOT / 'test-results/nas-parity/followup/console-queue-20261017'
    def read(path):
        return json.loads(path.read_text())
    qualification = read(folder / 'qualification-proof.json')
    deployment = read(folder / 'deployment/deployment-proof.json')
    assert qualification['all_passed'] and qualification['native_linux_tests'] == 6
    assert qualification['main_service_configuration_and_processes_unchanged']
    assert deployment['controller_image'] == qualification['candidate_image']
    assert all(deployment[k] is True for k in ('only_controller_recreated', 'seven_services_healthy',
               'runner_worker_database_and_dind_unchanged', 'configuration_files_unchanged', 'database_rows_unchanged'))
    assert not deployment['lease_deadlines_changed'] and not deployment['graphato_sources_tests_fixture_limits_changed']
    paths = [folder / 'qualification-proof.json', folder / 'deployment/deployment-proof.json']
    for name, sha in deployment['source_sha256'].items():
        assert vm.digest(vm.ROOT / 'src/leroy' / name) == sha
    for mode in ('legacy', 'bounded'):
        case = folder / ('worker-' + mode)
        result = read(case / 'result.json')
        measure = read(case / ('production-measurement-qualification-console-pipe-' + mode + '.json'))
        assert measure['native_jenkins_quiet_window_verified']
        assert result['run']['status'] == ('succeeded' if mode == 'bounded' else 'interrupted')
        assert all(row['direct_sql']['ok'] for row in result['samples'])
        if mode == 'bounded':
            assert all(row['api_live']['ok'] for row in result['samples']) and result['verified_artifacts']
        else:
            assert any(not row['api_live']['ok'] for row in result['samples'])
        paths.extend([case / 'result.json', case / ('production-measurement-qualification-console-pipe-' + mode + '.json')])
    measurement = folder / 'deployment/production-measurement-qualification-console-queue-deployment.json'
    assert read(measurement)['native_jenkins_quiet_window_verified']
    paths.append(measurement)
    if current:
        expected = repr(deployment['controller_image'])
        program = ("import json,subprocess\nc=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-controller-1'],timeout=20))[0]\n"
                   "assert c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'\n"
                   "assert c['Image']==" + expected + " and c['State']['Running'] and c['State']['Health']['Status']=='healthy'\nprint('{}')")
        vm.remote(program, sudo=True, timeout=45)
    return {'controller_image': deployment['controller_image'], 'lease_deadlines_changed': False,
            'original_graphato_acceptance_proven': False,
            'evidence_sha256': {p.relative_to(folder).as_posix(): vm.digest(p) for p in paths}}


def qualified_controller_image(previous, approval):
    """Accept only the verified logging layer on the qualified engine image."""
    if approval is None or approval.get('attempt') not in {'w', 'x', 'y'}:
        return previous
    value = binding()
    assert approval['console_logging_binding'] == value
    path = vm.ROOT / 'test-results/nas-parity/followup/console-queue-20261017/deployment/deployment-proof.json'
    assert json.loads(path.read_text())['previous_controller_image'] == previous
    return value['controller_image']
