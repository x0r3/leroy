"""Build and inspect the staged runtime image in the owned NAS Docker daemon."""

import json
import subprocess

from nas_followup_support import inner
from nas_gitea_target import idle
from nas_ssh import ROOT

RUNTIME = r"""
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import argon2 from 'argon2';
import Fastify from 'fastify';
import pg from 'pg';
assert.equal(process.getuid(),1000);
for(const name of ['typescript','vite','vitest']) assert(!fs.existsSync('/app/node_modules/'+name));
assert(fs.existsSync('/app/dist/server/entry-public.js'));
const hash=await argon2.hash('isolated-image-probe');
assert(await argon2.verify(hash,'isolated-image-probe'));
const server=Fastify(); server.get('/',()=>({ok:true}));
assert.equal((await server.inject('/')).statusCode,200); await server.close();
assert(new pg.Client());
const packages=[];
function visit(folder){
 const manifest=path.join(folder,'package.json');
 if(!fs.existsSync(manifest))return;
 const data=JSON.parse(fs.readFileSync(manifest,'utf8'));
 packages.push({path:path.relative('/app',folder),name:data.name,version:data.version});
 scan(path.join(folder,'node_modules'));
}
function scan(folder){
 if(!fs.existsSync(folder))return;
 for(const item of fs.readdirSync(folder,{withFileTypes:true})){
  if(item.name.startsWith('.')||!item.isDirectory())continue;
  const target=path.join(folder,item.name);
  if(item.name.startsWith('@'))for(const nested of fs.readdirSync(target))visit(path.join(target,nested));
  else visit(target);
 }
}
scan('/app/node_modules');
console.log(JSON.stringify({uid:process.getuid(),argon2_native_verified:true,fastify_injection_verified:true,development_tools_absent:true,packages}));
"""

PROGRAM = r"""
import json,os,pathlib,subprocess,time
root=pathlib.Path('/var/jenkins_home/workspace/antares-ci')
assert not subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()
subprocess.run(['git','fetch',SOURCE,COMMIT],cwd=root,check=True,capture_output=True)
subprocess.run(['git','checkout','--detach',COMMIT],cwd=root,check=True,capture_output=True)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==COMMIT
started=time.monotonic()
result=subprocess.run(['docker','build','--tag',IMAGE,'.'],cwd=root,timeout=1500)
report={'commit':COMMIT,'build_returncode':result.returncode,'build_seconds':time.monotonic()-started,'diagnostic_only':True,'cache_scope':'Existing Docker layers may be reused; this is runtime validation, not a cold-build benchmark'}
try:
 if result.returncode==0:
  report['image']=json.loads(subprocess.check_output(['docker','image','inspect',IMAGE],text=True))[0]['Id']
  runtime=json.loads(subprocess.check_output(['docker','run','--rm','--network','none','--memory','512m','--cpus','1',IMAGE,'node','--input-type=module','-e',RUNTIME],text=True,timeout=120))
  lock=json.loads((root/'package-lock.json').read_text())['packages']
  for package in runtime['packages']:
   assert lock[package['path']]['version']==package['version'],package
  direct=json.loads((root/'package.json').read_text())['dependencies']
  installed={p['path']:p['version'] for p in runtime['packages']}
  assert all(installed['node_modules/'+name]==version for name,version in direct.items())
  report.update(runtime=runtime,installed_versions_match_lock=True,all_direct_production_dependencies_present=True)
 report['passed']=result.returncode==0
finally:
 subprocess.run(['docker','image','rm',IMAGE],check=False,capture_output=True)
print('LEROY_IMAGE_PROBE_REPORT='+json.dumps(report),flush=True)
"""


def main():
    commit = subprocess.check_output(
        ["git", "-C", str(ROOT / ".sources/antares-nas-validation"), "rev-parse", "HEAD"], text=True
    ).strip()
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / commit
    staged = json.loads((folder / "staged.json").read_text())
    marker = folder / "focused-image.json"
    assert not marker.exists(), "No implicit diagnostic rerun"
    idle()
    assert json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}")) is False
    running = inner("ps", "--format", "{{.Names}}").splitlines()
    assert not any(name.startswith("antares-") for name in running), "Finish the other Antares probe"
    image = inner("inspect", "jenkins-parity", "--format", "{{.Image}}").strip()
    name = "antares-image-probe-" + commit[:12]
    program = (
        "\n".join(
            key + "=" + repr(value)
            for key, value in {
                "COMMIT": commit,
                "SOURCE": staged["source"],
                "IMAGE": "antares:probe-" + commit[:12],
                "RUNTIME": RUNTIME,
            }.items()
        )
        + "\n"
        + PROGRAM
    )
    print("Antares runtime image diagnostic:", commit, flush=True)
    try:
        output = inner(
            "run",
            "--name",
            name,
            "--label",
            "io.leroy.nas-parity=true",
            "--network",
            "leroy-jobs",
            "--volumes-from",
            "jenkins-parity",
            "--memory",
            "3g",
            "--cpus",
            "2",
            "--entrypoint",
            "python3",
            image,
            "-c",
            program,
            timeout=1800,
        )
        (folder / "focused-image.log").write_text(output, encoding="utf-8")
        report = json.loads(output.split("LEROY_IMAGE_PROBE_REPORT=", 1)[1])
        marker.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({key: value for key, value in report.items() if key != "runtime"}), flush=True)
        assert report["passed"]
    except Exception as error:
        if not marker.exists():
            output = inner("logs", name)
            (folder / "focused-image.log").write_text(output, encoding="utf-8")
            marker.write_text(
                json.dumps(
                    {"commit": commit, "diagnostic_only": True, "passed": False, "error": str(error)},
                    indent=2,
                )
                + "\n"
            )
        raise
    finally:
        inner("rm", "-f", name, timeout=90)


if __name__ == "__main__":
    main()
