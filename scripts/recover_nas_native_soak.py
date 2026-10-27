"""Resume the retained NAS preparation after correcting Docker stdin forwarding.

The failed attempt stays intact. Both extracted source trees and all transferred
inputs must match their original hashes before the import or worker build starts.
"""

import ast
import hashlib
import json
from datetime import datetime, timezone

from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, run_script
from prepare_nas_native_soak import COMMIT, FOLDER, PROGRAM, REMOTE, SOURCE_SHA


def main():
    assert not (FOLDER / 'prepared-inputs.json').exists(), 'Retain completed inputs'
    retained = ast.parse((FOLDER / 'preparation-program.py').read_text())
    keys = {'REMOTE', 'INNER', 'COMMIT', 'SOURCE_SHA', 'FILES', 'RUNTIME_REFERENCE',
            'RUNTIME_LAYERS', 'REGISTRY_DIGEST', 'WORKER_FILES', 'PROFILE_SHA'}
    parameters = {}
    for node in retained.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = node.targets[0].id if isinstance(node.targets[0], ast.Name) else None
            if name in keys:
                parameters[name] = ast.literal_eval(node.value)
    assert set(parameters) == keys and parameters['COMMIT'] == COMMIT
    assert parameters['SOURCE_SHA'] == SOURCE_SHA and parameters['REMOTE'] == REMOTE
    for name in ('nas-passive-http.py', 'nas-soak-case.py'):
        path = ROOT / 'scripts/diagnostics' / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == parameters['FILES'][name]
    attempt = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = ROOT / 'test-results/nas-parity/followup/nas-native-soak-import-recovery' / attempt
    folder.mkdir(parents=True, exist_ok=False)
    parameters.update(RESUME=True, ATTEMPT_DIR=REMOTE + '/recovery/' + attempt)
    program = '\n'.join(key + '=' + repr(value) for key, value in parameters.items()) + '\n' + PROGRAM
    compile(program, 'NAS immutable import recovery', 'exec')
    (folder / 'recovery-program.py').write_text(program, encoding='utf-8')
    before = begin(folder, 'recover-native-import')
    print(json.dumps({'resuming_owned_preparation': True, 'commit': COMMIT, 'attempt': attempt,
                      'source_and_tests_modified': False}), flush=True)
    try:
        response = run_script("python3 - <<'PY'\n" + program + "\nPY\n",
                              ROOT / '.local/nas-ssh.json', sudo=True, timeout=3000)
    finally:
        finish(folder, 'recover-native-import', before)
    private = ROOT / '.local/nas-native-soak' / attempt
    private.mkdir(parents=True, exist_ok=False)
    (private / 'stdout.log').write_text(response.stdout, encoding='utf-8')
    (private / 'stderr.log').write_text(response.stderr, encoding='utf-8')
    receipt = {'exit_code': response.returncode,
               'stdout_sha256': hashlib.sha256(response.stdout.encode()).hexdigest(),
               'stderr_sha256': hashlib.sha256(response.stderr.encode()).hexdigest(),
               'remote_attempt': parameters['ATTEMPT_DIR'], 'source_or_tests_modified': False,
               'tests_started': False}
    (folder / 'recovery-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    if response.returncode:
        print(json.dumps({'preparation_failed': True, 'attempt': attempt,
                          'stderr_tail': response.stderr[-1800:]}), flush=True)
        raise RuntimeError('Preserved NAS import recovery failure; no original test was started')
    lines = response.stdout.splitlines()
    inputs = json.loads(lines[-1])
    assert inputs['commit'] == COMMIT and inputs['source_sha256'] == SOURCE_SHA
    (folder / 'prepared-inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
    (FOLDER / 'prepared-inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
    print(json.dumps({'immutable_inputs_prepared': True, 'inputs': inputs}), flush=True)


if __name__ == '__main__':
    main()
