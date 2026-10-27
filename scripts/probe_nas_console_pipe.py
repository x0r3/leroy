"""Compare real CI workers with an unread controller output pipe, on the NAS."""

import argparse
import json

import nas_release_vm as vm
from nas_followup_support import production_jobs_program
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, run_script

BASE = ROOT / 'test-results/nas-parity/followup/console-queue-20261017'

BOOTSTRAP = r'''
import json,logging,os,pathlib,threading,time,uvicorn
root=pathlib.Path('/data')
reader,writer=os.pipe()
os.dup2(writer,1);os.dup2(writer,2);os.close(writer)
def drain():
 while not (root/'drain-logging.flag').exists():time.sleep(0.1)
 while os.read(reader,65536):pass
def flood():
 while not (root/'inject-logging.flag').exists():time.sleep(0.1)
 at=time.monotonic();value={'started':True,'error':None,'lines':0}
 (root/'flood-start.json').write_text(json.dumps(value))
 try:
  for _ in range(2048):
   logging.getLogger('uvicorn.error').warning('CONSOLE PIPE PRESSURE '+'x'*1024)
   value['lines']+=1
 except Exception as e:value['error']=type(e).__name__
 value['duration_seconds']=time.monotonic()-at
 (root/'flood-result.json').write_text(json.dumps(value))
threading.Thread(target=drain,daemon=True).start()
threading.Thread(target=flood,daemon=True).start()
if BOUNDED:
 from leroy.console_logging import logging_config
 config=logging_config()
else:config=uvicorn.config.LOGGING_CONFIG
uvicorn.run('leroy.api:create_app',factory=True,host='0.0.0.0',port=8088,log_config=config)
'''


def program(mode, candidate, production_program):
    source = (ROOT / 'scripts/diagnostics/nas-control-log-pressure.py').read_text()

    def replace(old, new):
        nonlocal source
        assert source.count(old) == 1, 'Review the changed diagnostic before adapting it'
        source = source.replace(old, new)

    replace('phase = MODE.replace("-", "") + ATTEMPT', 'phase = "pipe" + MODE.replace("-", "") + ATTEMPT')
    replace('root / "control-latency-20261012" / phase', 'root / "console-pipe-20261017" / phase')
    start = source.index('bootstrap = r"""')
    end = source.index('\n(work / "bootstrap.py")', start)
    source = source[:start] + 'bootstrap = ' + repr('BOUNDED=' + repr(mode == 'bounded') + '\n' + BOOTSTRAP) + '\n' + source[end:]
    replace('assert MODE in ("blocking", "non-blocking")', 'assert MODE in ("legacy", "bounded")')
    start = source.index('    "--log-driver",')
    end = source.index('for key, value in environment.items():', start)
    source = source[:start] + ''']
assert actual['controller']['HostConfig']['LogConfig']['Type']=='json-file'
assert actual['controller']['HostConfig']['LogConfig']['Config']['mode']=='non-blocking'
controller_args += ['--log-driver','json-file']
for key,value in actual['controller']['HostConfig']['LogConfig']['Config'].items():
 controller_args += ['--log-opt',key+'='+value]
''' + source[end:]
    replace('    actual["controller"]["Image"],', '    CANDIDATE if MODE=="bounded" else actual["controller"]["Image"],')
    replace('while time.monotonic() - started < 70', 'while time.monotonic() - started < 120')
    replace('    read_allowed.set()\n    assert not warnings', '    read_allowed.set()\n    (work / "data/drain-logging.flag").touch()\n    assert not warnings')
    replace('finally:\n    read_allowed.set()', 'finally:\n    (work / "data/drain-logging.flag").touch()\n    read_allowed.set()')
    replace('"Synthetic log-delivery stall on a separate control database and real job; not historical HDD causality proof"',
            '"Unread initial OS stdout/stderr pipe for 120s; separate controller/database and real worker; not proof of historical HDD causality"')
    compile(source, '<reviewed-console-probe>', 'exec')
    return ('MODE=' + repr(mode) + '\nATTEMPT=""\nEXPECT_BUFFERED_WORKER=True\nCANDIDATE='
            + repr(candidate) + '\nPRODUCTION_PROGRAM=' + repr(production_program) + '\n' + source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['legacy', 'bounded'])
    mode = parser.parse_args().mode
    proof = json.loads((BASE / 'qualification-proof.json').read_text())
    assert proof['all_passed'] and proof['main_service_configuration_and_processes_unchanged']
    idle()
    assert not vm.state()['State']['Running']
    folder = BASE / ('worker-' + mode)
    folder.mkdir(exist_ok=True)
    assert not (folder / 'program.py').exists(), 'Retain an uncertain probe before dispatching another CI run'
    before = begin(folder, 'console-pipe-' + mode)
    production_program = production_jobs_program(history=False)
    source = program(mode, proof['candidate_image'], production_program)
    (folder / 'program.py').write_text(source)
    result = run_script("python3 - <<'PY'\n" + source + '\nPY\n', vm.CREDENTIALS, sudo=True, timeout=720)
    (folder / 'stdout.log').write_text(result.stdout)
    (folder / 'stderr.log').write_text(result.stderr)
    finish(folder, 'console-pipe-' + mode, before)
    assert result.returncode == 0, 'Inspect retained probe evidence; do not implicitly repeat a CI run'
    value = json.loads(result.stdout.splitlines()[-1])
    assert value['run']['status'] == ('succeeded' if mode == 'bounded' else 'interrupted')
    assert all(row['direct_sql']['ok'] for row in value['samples'])
    if mode == 'bounded':
        assert all(row['api_live']['ok'] for row in value['samples']) and value['verified_artifacts']
    else:
        assert any(not row['api_live']['ok'] for row in value['samples'])
    (folder / 'result.json').write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({'mode': mode, 'run_id': value['run']['id'], 'status': value['run']['status'],
                      'api_timeout_samples': sum(not row['api_live']['ok'] for row in value['samples']),
                      'verified_artifacts': value['verified_artifacts']}))


if __name__ == '__main__':
    main()
