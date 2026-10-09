"""Reproduce a captured target permission precondition with unchanged source in a temporary fixture."""

import hashlib
import json
import subprocess
from datetime import datetime, timezone

from nas_ssh import ROOT
from prepare_nas_vm import guest
from stage_nas_production_graphato import COMMIT

PROGRAM = r'''
import hashlib,importlib.util,json,pathlib,stat,tempfile
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
assert hashlib.sha256(SOURCE.encode()).hexdigest()==SOURCE_SHA
with tempfile.TemporaryDirectory(prefix='leroy-marker-precondition-') as temporary:
 root=pathlib.Path(temporary);helper=root/'postdeploy.py';helper.write_text(SOURCE)
 spec=importlib.util.spec_from_file_location('unchanged_marker_precondition',helper)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 state=root/'control';state.mkdir(mode=int(CONTROL['mode'],8))
 assert state.stat().st_uid==CONTROL['uid']==0
 assert stat.S_IMODE(state.stat().st_mode)==int(CONTROL['mode'],8)==0o755
 module.STATE=state
 try:module.run_marker('0'*32)
 except ValueError as error:failure=str(error)
 else:raise AssertionError('Captured precondition unexpectedly passed')
 assert failure=='Run markers require root-private directories' and not list(state.iterdir())
 state.chmod(0o700)
 marker=module.run_marker('0'*32)
 assert marker==state/'runs'/('0'*32+'.json') and not marker.exists()
 assert stat.S_IMODE((state/'runs').stat().st_mode)==0o700
print(json.dumps({'original_marker_validation_error':failure,'captured_mode_reproduced':True,'root_private_mode_accepts_marker_path':True,'application_source_sha256':SOURCE_SHA,'temporary_fixture_removed':not root.exists(),'actual_application_directory_modified':False,'application_patches_applied':False,'production_modified':False}))
'''


def main():
    base = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / COMMIT
    destination = base / 'marker-precondition-reproduction.json'
    assert not destination.exists(), 'Retain the first reproduction'
    captured = base / 'graphato-ci/jenkins-final-state.json'
    target = json.loads(captured.read_text())
    control = target['postdeploy_control_directory']
    assert control['exists'] and control['is_directory'] and not control['is_symlink']
    assert control['mode'] == '0o755' and control['uid'] == 0
    checkout = ROOT / '.sources/production-review/graphato-ed21c2e6346a'
    assert subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip() == COMMIT
    source = (checkout / 'deployments/linux/host/postdeploy.py').read_text(encoding='utf-8')
    digest = hashlib.sha256(source.encode()).hexdigest()
    assert digest == target['manifest']['files']['deployments/linux/host/postdeploy.py']
    program = f'SOURCE={source!r}\nSOURCE_SHA={digest!r}\nCONTROL={control!r}\n' + PROGRAM
    record = json.loads(guest('sudo python3 -B -', program, timeout=30))
    record.update(at=datetime.now(timezone.utc).isoformat(), commit=COMMIT,
                  captured_target_evidence=captured.relative_to(ROOT).as_posix(),
                  captured_target_precondition=control,
                  scope='Reconstructed captured Jenkins directory precondition in temporary Linux fixture; no claim of a runtime probe on the restored Jenkins target')
    destination.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
