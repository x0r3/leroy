"""Small original-worker fault probes in the owned stack, without Graphato or paused NAS services."""
import json
import subprocess
import time
from contextlib import closing

import nas_native
from compare_nas_antares import client
from nas_followup_support import production_jobs
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_progress import publish
from nas_ssh import ROOT

FOLDER = ROOT / 'test-results/nas-parity/followup/resident-control-probe-20261017'
PIPELINE = 'nas-resident-control-probe-20261017'


def call(arguments, timeout=30):
    result = subprocess.run(arguments, capture_output=True, timeout=timeout)
    assert result.returncode == 0, 'Owned diagnostic operation failed; inspect protected evidence'
    return result.stdout


def main():
    nas_native.validate(ROOT)
    idle()
    vm = json.loads(call(['docker', 'inspect', 'leroy-nas-release-target-vm']))[0]
    assert not vm['State']['Running']
    outer = json.loads(call(['docker', 'inspect', 'leroy-nas-parity-docker-1']))[0]
    controller = json.loads(call(['docker', 'inspect', 'leroy-nas-parity-controller-1']))[0]
    assert all(c['Config']['Labels']['com.docker.compose.project'] == 'leroy-nas-parity' for c in (outer, controller))
    prefix = ['docker', 'exec', outer['Id'], 'docker']
    FOLDER.mkdir()
    before = begin(FOLDER, 'resident-control')
    spec = {'id': PIPELINE, 'name': 'NAS control recovery probe', 'group': 'Diagnostics',
            'profile': 'graphato', 'timeout': 300, 'enabled': False, 'steps': [{
                'id': 'hold', 'name': 'Wait without external effects', 'timeout': 220,
                'command': ['python', '-c', "import time,pathlib;time.sleep(145);pathlib.Path('receipt.txt').write_text('completed')"],
                'artifacts': ['receipt.txt']}]}
    with closing(client()) as api:
        response = api.get('/api/pipelines')
        response.raise_for_status()
        assert PIPELINE not in {p['id'] for p in response.json()}, 'Retain existing diagnostic; do not dispatch twice'
        response = api.put('/api/pipelines/' + PIPELINE, json=spec)
        response.raise_for_status()
        outcomes = []
        for name, duration in (('brief-and-controller-restart', 18), ('expired-lease', 110)):
            publish(FOLDER / (name + '-intent.json'), {'at_epoch': time.time(), 'dispatched_once': True})
            response = api.post('/api/pipelines/' + PIPELINE + '/runs', json={})
            response.raise_for_status()
            run = response.json()
            run_id = run['id']
            publish(FOLDER / (name + '-start.json'), run)
            worker_name = 'leroy-' + run_id
            deadline = time.monotonic() + 260
            worker = None
            while time.monotonic() < deadline - 160:
                result = subprocess.run(prefix + ['inspect', worker_name], capture_output=True, timeout=20)
                if result.returncode == 0:
                    worker = json.loads(result.stdout)[0]
                    assert worker['Config']['Labels']['io.leroy.run'] == run_id
                    assert worker['Config']['Labels']['io.leroy.runner'] == 'runner-nas-parity'
                    response = api.get('/api/runs/' + run_id)
                    response.raise_for_status()
                    if response.json()['steps'][0]['status'] == 'running':
                        break
                time.sleep(2)
            else:
                raise RuntimeError('Known probe did not start')
            network, = worker['NetworkSettings']['Networks']
            timer = 'leroy-probe-link-restore-' + run_id
            call(['systemd-run', '--unit=' + timer, '--on-active=130s', '--property=Type=oneshot',
                  *prefix, 'network', 'connect', network, worker['Id']])
            detached = False
            try:
                call(prefix + ['network', 'disconnect', network, worker['Id']])
                detached = True
                publish(FOLDER / (name + '-disconnected.json'), {'at_epoch': time.time(), 'seconds': duration})
                until = time.monotonic() + duration
                while time.monotonic() < until:
                    production = production_jobs()
                    assert not production['active_builds'], 'Stop own probe for productive Jenkins'
                    time.sleep(min(5, max(0, until - time.monotonic())))
            finally:
                result = subprocess.run(prefix + ['inspect', worker['Id']], capture_output=True, timeout=20)
                if result.returncode == 0:
                    current = json.loads(result.stdout)[0]
                    assert current['Id'] == worker['Id'] and current['Config']['Labels']['io.leroy.run'] == run_id
                    if detached and network not in current['NetworkSettings']['Networks']:
                        call(prefix + ['network', 'connect', network, worker['Id']])
                call(['systemctl', 'stop', timer + '.timer'])
            if name == 'brief-and-controller-restart':
                time.sleep(5)
                current = json.loads(call(['docker', 'inspect', controller['Id']]))[0]
                assert current['Image'] == controller['Image']
                call(['docker', 'restart', '--time', '10', controller['Id']], timeout=35)
                publish(FOLDER / 'controller-restarted.json', {'at_epoch': time.time(), 'same_image': True})
            while time.monotonic() < deadline:
                try:
                    response = api.get('/api/runs/' + run_id)
                    response.raise_for_status()
                    run = response.json()
                except Exception:
                    time.sleep(2)
                    continue
                if run['status'] not in ('queued', 'running', 'waiting'):
                    break
                production = production_jobs()
                assert not production['active_builds'], 'Stop own probe for productive Jenkins'
                time.sleep(3)
            publish(FOLDER / (name + '-run.json'), run)
            assert run['id'] == run_id
            if name == 'brief-and-controller-restart':
                assert run['status'] == 'succeeded'
            else:
                assert run['status'] in ('cancelled', 'interrupted') and 'lease' in run['reason'].lower()
            outcomes.append({'case': name, 'run_id': run_id, 'status': run['status'], 'reason': run['reason']})
        response = api.get('/api/runs', params={'pipeline': PIPELINE})
        response.raise_for_status()
        assert {r['id'] for r in response.json()} == {r['run_id'] for r in outcomes}
        publish(FOLDER / 'result.json', {'all_passed': True, 'outcomes': outcomes, 'no_duplicate_runs': True,
                'worker_cutoff_seconds': 45, 'server_lease_seconds': 90,
                'graphato_started': False, 'seven_services_paused': False, 'production_modified': False})
    finish(FOLDER, 'resident-control', before)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Only runs journaled by this probe are eligible for cancellation.
        with closing(client()) as api:
            for marker in FOLDER.glob('*-start.json'):
                retained = json.loads(marker.read_text())
                response = api.get('/api/runs/' + retained['id'])
                response.raise_for_status()
                run = response.json()
                assert run['pipeline_id'] == PIPELINE
                if run['status'] in ('queued', 'running', 'waiting'):
                    api.post('/api/runs/' + run['id'] + '/cancel', json={}).raise_for_status()
        raise
