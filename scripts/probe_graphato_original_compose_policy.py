"""Run the original failing policy test on the owned target; never deploy an application."""

import hashlib
import json
import subprocess
from datetime import datetime, timezone

from nas_ssh import ROOT
from prepare_nas_vm import guest
from stage_nas_production_graphato import COMMIT

PROGRAM = r'''
import hashlib,importlib.util,io,json,os,pathlib,subprocess,unittest
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
root=pathlib.Path('/tmp/leroy-graphato-config-'+COMMIT[:12]);assert not root.exists()
root.mkdir(mode=0o700)
for name,text in SOURCES.items():
 path=root/name;assert path.resolve().is_relative_to(root.resolve())
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
 assert hashlib.sha256(path.read_bytes()).hexdigest()==HASHES[name]
spec=importlib.util.spec_from_file_location('test_host',root/'deployments/linux/host/test_host.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
name='test_current_production_compose_passes_release_policy'
stream=io.StringIO()
result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.TestSuite([module.ReleaseBoundary(name)]))
test=module.ReleaseBoundary(name);test.setUp()
try:
 test.manifest['runtimeImageId']=test.manifest['imageId']
 test.manifest['agentTestWorker']['runtimeImageId']=test.manifest['agentTestWorker']['imageId']
 environment={k:v for k,v in os.environ.items() if not k.startswith(('GRAPHATO_','COMPOSE_','DOCKER_'))}
 environment.update(GRAPHATO_SECRETS_DIR=str(test.directory),GRAPHATO_SERVER_IMAGE=test.manifest['runtimeImageId'],GRAPHATO_AGENT_TEST_IMAGE=test.manifest['agentTestWorker']['runtimeImageId'])
 command=['docker','compose','-f','compose.prod.yaml','-f','deployments/linux/compose.host.yaml','-f','compose.agent-tests.yaml','-f','deployments/linux/compose.agent-tests.prod.yaml','config','--format','json']
 rendered=subprocess.run(command,cwd=root,env=environment,capture_output=True,text=True,timeout=30)
 assert rendered.returncode==0,rendered.stderr[-1000:]
 server=json.loads(rendered.stdout)['services']['server']
 preview=[v for v in server['volumes'] if v.get('target')=='/run/graphato-preview'];assert len(preview)==1
 projection={'GRAPHATO_PREVIEW_INGRESS_DIR':server.get('environment',{}).get('GRAPHATO_PREVIEW_INGRESS_DIR'),'preview_mount':preview[0]}
finally:test.doCleanups()
print(json.dumps({'test':name,'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'skipped':len(result.skipped),'successful':result.wasSuccessful(),'output':stream.getvalue(),'compose_version':subprocess.check_output(['docker','compose','version'],text=True).strip(),'rendered_policy_projection':projection,'source_hashes':HASHES,'application_deployed':False,'application_patches_applied':False,'production_modified':False}))
'''


def main():
    source = ROOT / ".sources/production-review/graphato-ed21c2e6346a"
    assert subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() == COMMIT
    names = ["compose.prod.yaml", "compose.agent-tests.yaml", "deployments/linux/compose.host.yaml",
             "deployments/linux/compose.agent-tests.prod.yaml", "deployments/linux/host/release.py",
             "deployments/linux/host/registry.py", "deployments/linux/host/test_host.py", "scripts/deploy-remote.py"]
    sources = {name: (source / name).read_text(encoding="utf-8") for name in names}
    hashes = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in sources.items()}
    folder = ROOT / "test-results/nas-parity/followup/production-source-review/failed-groups"
    destination = folder / "original-compose-policy-probe.json"
    assert not destination.exists(), "No implicit repetition"
    program = f"COMMIT={COMMIT!r}\nSOURCES={sources!r}\nHASHES={hashes!r}\n" + PROGRAM
    record = json.loads(guest("python3 -B -", program, timeout=90))
    record.update(at=datetime.now(timezone.utc).isoformat(), commit=COMMIT,
                  scope="Original policy unit test and config rendering on owned Linux application target; not a full pipeline result")
    destination.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))


if __name__ == "__main__":
    main()
