"""Collect optional diagnostics after VM shutdown without cancelling original CI."""

import json
import time

import nas_release_vm as vm
from nas_worker_control_trace import collect_worker_trace


def collect_optional_trace(folder):
    proof = folder / 'worker-control-trace.json'
    completed = folder / 'worker-control-trace-collection.json'
    if not proof.exists():
        return {'status': 'not_started'}
    if completed.exists():
        return json.loads(completed.read_text())
    try:
        if vm.state()['State']['Running']:
            return {'status': 'deferred_until_vm_shutdown', 'original_ci_restarted': False}
        outcome = collect_worker_trace(folder)
        result = {'status': 'collected', 'outcome': outcome}
    except Exception as error:
        # Observability failures must not cancel an original pipeline or expose
        # exception text containing credentials, commands or request data.
        result = {'status': 'observation_failed', 'error_type': type(error).__name__}
    result.update(at_epoch=time.time(), original_ci_restarted=False)
    temporary = completed.with_suffix('.pending')
    temporary.write_text(json.dumps(result, indent=2) + '\n')
    temporary.replace(completed)
    return result
