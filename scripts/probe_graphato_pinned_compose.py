"""Render the unchanged policy with its immutable original Docker CLI image, without a socket."""

import json
import re
from datetime import datetime, timezone

from nas_ssh import ROOT
from prepare_nas_vm import guest
from stage_nas_production_graphato import COMMIT

PROGRAM = r'''
import importlib.util,json,os,pathlib,subprocess
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
root=pathlib.Path('/tmp/leroy-graphato-config-'+COMMIT[:12]);assert root.is_dir() and not root.is_symlink()
owner=root.stat()
spec=importlib.util.spec_from_file_location('test_host',root/'deployments/linux/host/test_host.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
test=module.ReleaseBoundary('test_current_production_compose_passes_release_policy');test.setUp()
try:
 test.manifest['runtimeImageId']=test.manifest['imageId']
 test.manifest['agentTestWorker']['runtimeImageId']=test.manifest['agentTestWorker']['imageId']
 subprocess.run(['docker','pull',IMAGE],check=True,capture_output=True,text=True,timeout=120)
 identity=subprocess.check_output(['docker','image','inspect',IMAGE,'--format','{{.Id}}'],text=True).strip()
 prefix=['docker','run','--rm','--name','leroy-graphato-compose-policy-probe','--label','io.leroy.parity.diagnostic=graphato-compose-cli','--user',str(owner.st_uid)+':'+str(owner.st_gid),'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','128m','--memory-swap','128m','--cpus','1','--pids-limit','64','--mount','type=bind,src='+str(root)+',dst=/source,readonly','--workdir','/source','--env','GRAPHATO_SECRETS_DIR=/fixture-secrets','--env','GRAPHATO_SERVER_IMAGE='+test.manifest['runtimeImageId'],'--env','GRAPHATO_AGENT_TEST_IMAGE='+test.manifest['agentTestWorker']['runtimeImageId'],IMAGE]
 version=subprocess.check_output([*prefix,'docker','compose','version'],text=True,timeout=30).strip()
 command=['docker','compose','-f','compose.prod.yaml','-f','deployments/linux/compose.host.yaml','-f','compose.agent-tests.yaml','-f','deployments/linux/compose.agent-tests.prod.yaml','config','--format','json']
 rendered=subprocess.run([*prefix,*command],capture_output=True,text=True,timeout=30)
 assert rendered.returncode==0,rendered.stderr[-1000:]
 config=json.loads(rendered.stdout);server=config['services']['server']
 preview=[v for v in server['volumes'] if v.get('target')=='/run/graphato-preview'];assert len(preview)==1
 try:module.release.check_config(config,test.manifest);error=None
 except ValueError as exception:error=str(exception)
 projection={'GRAPHATO_PREVIEW_INGRESS_DIR':server.get('environment',{}).get('GRAPHATO_PREVIEW_INGRESS_DIR'),'preview_mount':preview[0]}
 remaining=subprocess.check_output(['docker','ps','-aq','--filter','name=^/leroy-graphato-compose-policy-probe$'],text=True).strip()
 assert not remaining
finally:test.doCleanups()
print(json.dumps({'image':IMAGE,'image_id':identity,'compose_version':version,'rendered_policy_projection':projection,'policy_error':error,'policy_passed':error is None,'no_docker_socket':True,'network_disabled':True,'container_removed':True,'application_deployed':False,'application_patches_applied':False,'production_modified':False}))
'''


def main():
    source = ROOT / ".sources/production-review/graphato-ed21c2e6346a"
    dockerfile = (source / "deployments/linux/Dockerfile").read_text()
    image, = re.findall(r"^FROM (docker:28\.5\.2-cli@sha256:[0-9a-f]{64}) AS docker-cli$", dockerfile, re.MULTILINE)
    folder = ROOT / "test-results/nas-parity/followup/production-source-review/failed-groups"
    destination = folder / "pinned-compose-policy-probe.json"
    assert not destination.exists(), "No implicit repetition"
    program = f"COMMIT={COMMIT!r}\nIMAGE={image!r}\n" + PROGRAM
    record = json.loads(guest("sudo python3 -B -", program, timeout=180))
    record.update(at=datetime.now(timezone.utc).isoformat(), commit=COMMIT,
                  scope="Original immutable CLI image and policy validator; no full workload or execution-engine equivalence asserted")
    destination.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))


if __name__ == "__main__":
    main()
