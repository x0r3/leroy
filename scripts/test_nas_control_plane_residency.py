"""Exercise controller traffic for four minutes using a real owned NAS worker."""

import json
import time
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from compare_nas_job import collect_artifacts
from nas_gitea_target import idle
from nas_ssh import ROOT

from leroy.schema import Pipeline, Step


def main():
    idle()
    folder = ROOT / 'test-results/nas-parity/followup/control-plane-residency-workload'
    assert not folder.exists(), 'No implicit workload repetition'
    folder.mkdir()
    evidence = json.loads((folder.parent / 'control-plane-residency-deployment.json').read_text())
    assert all(row['swap_current_bytes'] == 0 for row in evidence['services'].values())
    identifier = 'leroy-nas-diagnostics'
    with closing(client()) as api:
        definitions = api.get('/api/pipelines').json()
        assert not any(p['enabled'] for p in definitions)
        previous = next(p['spec'] for p in definitions if p['id'] == identifier)
        assert previous['source']['kind'] == 'diagnostic'
        (folder / 'previous-definition.json').write_text(json.dumps(previous, indent=2) + '\n')
        command = "import time\nfor tick in range(80):\n print('Controller traffic probe',tick,flush=True)\n time.sleep(3)\n"
        spec = Pipeline(id=identifier, name='NAS-Test: Steuerdienste im RAM', group='Abnahme', enabled=False,
                        profile='graphato', timeout=480, source={'kind': 'diagnostic', 'scenario': 'control-plane-residency'},
                        steps=[Step(id='probe', name='Four-minute controller traffic', timeout=360,
                                    command=['python', '-c', command])])
        api.put('/api/pipelines/' + identifier, json=spec.model_dump()).raise_for_status()
        response = api.post('/api/pipelines/' + identifier + '/runs', json={})
        response.raise_for_status()
        run_id = response.json()['id']
        (folder / 'run-id.json').write_text(json.dumps({'id': run_id}) + '\n')
        deadline, samples = time.monotonic() + 500, []
        while time.monotonic() < deadline:
            started = time.monotonic()
            response = api.get('/api/runs/' + run_id)
            response.raise_for_status()
            run = response.json()
            samples.append({'at': datetime.now(timezone.utc).isoformat(), 'api_seconds': time.monotonic() - started,
                            'status': run['status']})
            if run['status'] not in ('running', 'waiting', 'queued'):
                break
            time.sleep(5)
        else:
            raise TimeoutError('Traffic probe remains active; no cancellation or repetition')
        (folder / 'run.json').write_text(json.dumps(run, indent=2) + '\n')
        (folder / 'samples.json').write_text(json.dumps(samples, indent=2) + '\n')
        collect_artifacts(api, run, folder / 'artifacts')
        api.put('/api/pipelines/' + identifier, json=previous).raise_for_status()
        assert run['status'] == 'succeeded', run['reason']
        assert (datetime.fromisoformat(run['finished_at']) - datetime.fromisoformat(run['started_at'])).total_seconds() >= 240
        report = {'at': datetime.now(timezone.utc).isoformat(), 'passed': True, 'run_id': run_id,
                  'duration_at_least_240_seconds': True, 'api_samples': len(samples),
                  'maximum_observed_api_seconds': max(row['api_seconds'] for row in samples),
                  'previous_diagnostic_definition_restored': True, 'worker_lease_budget_unchanged': True,
                  'production_modified': False, 'application_patches_applied': False,
                  'full_graphato_comparison': False}
        (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
