"""Read release identity, target health and published desktop payloads in the test environment."""

import argparse
import json
from datetime import datetime, timezone

from deploy_nas_parity import CREDENTIALS
from nas_candidate_paths import comparison_source
from nas_ssh import run_script
from prepare_nas_vm import guest

VM_PROGRAM = r"""
import hashlib,importlib.util,json,os,pathlib,stat,subprocess,urllib.request,urllib.error
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
release=pathlib.Path('/opt/graphato/current').resolve(strict=True)
assert release.parent==pathlib.Path('/opt/graphato/releases')
manifest=json.loads((release/'manifest.json').read_text())
assert manifest['commit']==COMMIT
receipt=json.loads(subprocess.check_output(['/usr/local/sbin/graphato-ci-receive'],env={**os.environ,'SSH_ORIGINAL_COMMAND':'release-status '+COMMIT},text=True))
assert receipt['commit']==COMMIT and receipt['activeRelease']
ids=subprocess.check_output(['docker','ps','-aq','--filter','label=com.docker.compose.project=graphato-prod'],text=True).split()
containers=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True)) if ids else []
rows=[]
for c in containers:
 state=c['State'];config=c['HostConfig']
 rows.append({'service':c['Config']['Labels']['com.docker.compose.service'],'image':c['Image'],'running':state['Running'],'health':state.get('Health',{}).get('Status'),'restart_count':c['RestartCount'],'apparmor':c['AppArmorProfile'],'read_only':config['ReadonlyRootfs'],'cap_drop':config['CapDrop'],'privileged':config['Privileged']})
token=pathlib.Path('/etc/graphato/secrets/server-token').read_text().strip()
probes={}
for url in ['http://127.0.0.1:8042/api/v1/info','https://graphato.test/api/v1/info']:
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'Authorization':'Bearer '+token}),timeout=15) as response:
   info=json.load(response)
   probes[url]={'status':response.status,'protocolVersion':info.get('protocolVersion'),'database':info.get('database'),'build':info.get('build')}
 except Exception as error:probes[url]={'error_type':type(error).__name__}
try:
 with urllib.request.urlopen('http://127.0.0.1:8042/api/v1/info',timeout=10) as response:anonymous=response.status
except urllib.error.HTTPError as error:anonymous=error.code
source=release/'verification-source.tar.gz'
with source.open('rb') as stream:source_digest=hashlib.file_digest(stream,'sha256').hexdigest()
assert source_digest==manifest['files']['verification-source.tar.gz']
control=pathlib.Path('/var/lib/graphato-host/postdeploy')
control_state={'exists':control.exists()}
if control.exists():
 info=control.lstat();control_state.update(mode=oct(stat.S_IMODE(info.st_mode)),uid=info.st_uid,gid=info.st_gid,is_directory=stat.S_ISDIR(info.st_mode),is_symlink=stat.S_ISLNK(info.st_mode))
 if control_state['is_directory'] and not control_state['is_symlink'] and control_state['mode']=='0o755' and control_state['uid']==0 and not list(control.iterdir()):
  helper=release/'deployments/linux/host/postdeploy.py'
  assert hashlib.sha256(helper.read_bytes()).hexdigest()==manifest['files']['deployments/linux/host/postdeploy.py']
  spec=importlib.util.spec_from_file_location('original_postdeploy_control_probe',helper)
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  assert module.STATE==control
  try:module.run_marker('0'*32)
  except ValueError as error:control_state['original_marker_validation_error']=str(error)
  else:raise AssertionError('Unexpected original marker validation outcome')
  assert not list(control.iterdir()) and control.lstat().st_mode==info.st_mode
  control_state['diagnostic_created_files']=False
print(json.dumps({'manifest':manifest,'receipt':receipt,'containers':sorted(rows,key=lambda r:r['service']),'health_probes':probes,'anonymous_status':anonymous,'verification_source_sha256':source_digest,'postdeploy_control_directory':control_state}))
"""

NAS_PROGRAM = r"""
import hashlib,io,json,pathlib,subprocess,tarfile,zipfile
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
prefix=['docker','exec','leroy-nas-parity-docker-1']
names=subprocess.check_output([*prefix,'find',DIRECTORY,'-maxdepth','1','-type','f','-name','*.zip.json'],text=True,timeout=30).splitlines()
selected=[]
for name in names:
 path=pathlib.PurePosixPath(name)
 assert path.parent==pathlib.PurePosixPath(DIRECTORY)
 value=subprocess.check_output([*prefix,'cat',name],timeout=30)
 assert len(value)<65536
 manifest=json.loads(value)
 if manifest['sourceCommit']==COMMIT and manifest['buildTimestamp']==BUILD_TIMESTAMP:
  artifact=pathlib.PurePosixPath(manifest['artifact'])
  assert len(artifact.parts)==1 and artifact.name not in {'.','..'} and artifact.suffix=='.zip'
  assert 0<manifest['sizeBytes']<32*1024*1024
  selected.append((path.name,artifact.name))
assert len(selected)==1,'Expected exactly one publication for this candidate build'
manifest_name,artifact_name=selected[0]
raw=subprocess.check_output([*prefix,'tar','-cf','-','-C',DIRECTORY,manifest_name,artifact_name,'graphato-desktop-latest.zip'],timeout=60)
assert len(raw)<64*1024*1024
rows=[]
with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
 members={p.name.removeprefix('./'):p for p in archive}
 for name,item in members.items():
  if not name.endswith('.zip.json'):continue
  manifest=json.load(archive.extractfile(item))
  if manifest['sourceCommit']!=COMMIT or manifest['buildTimestamp']!=BUILD_TIMESTAMP:continue
  payload=archive.extractfile(members[manifest['artifact']]).read()
  assert len(payload)==manifest['sizeBytes'] and hashlib.sha256(payload).hexdigest()==manifest['sha256']
  latest=archive.extractfile(members['graphato-desktop-latest.zip']).read()
  assert latest==payload
  with zipfile.ZipFile(io.BytesIO(payload)) as portable:
   assert portable.testzip() is None
   names=portable.namelist()
   assert set(names)=={'Graphato.exe','Graphato.portable','GraphatoData/','README-portable.txt','build-info.json'}
   assert portable.read('Graphato.exe')[:2]==b'MZ'
   build=json.loads(portable.read('build-info.json'))
   assert all(build[k]==manifest[k] for k in build)
   files={p.filename:{'size':p.file_size,'sha256':hashlib.sha256(portable.read(p)).hexdigest()} for p in portable.infolist()}
  rows.append({'manifest':manifest,'files':files,'latest_matches':True,'crc_verified':True})
assert len(rows)==1,'Expected exactly one verified publication for this candidate build'
print(json.dumps(rows))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", choices=["jenkins", "leroy"])
    parser.add_argument("--phase", choices=["delivery", "final"], default="final")
    parser.add_argument("--target-only", action="store_true", help="Collect the VM evidence without NAS SSH")
    parser.add_argument(
        "--via-leroy", action="store_true", help="Read the isolated publication through a manual worker"
    )
    parser.add_argument("--candidate")
    args = parser.parse_args()
    source, folder = comparison_source("graphato-ci", args.candidate)
    commit = source["commit"]
    state = json.loads(guest("sudo python3 -", f"COMMIT={commit!r}\n" + VM_PROGRAM, timeout=90))
    pair = json.loads((folder / "pair.json").read_text())
    artifacts = folder / (
        f"jenkins-{pair['jenkins']['number']}-artifacts" if args.engine == "jenkins" else "leroy-artifacts"
    )
    (expected_path,) = artifacts.rglob("release-manifest.json")
    expected = json.loads(expected_path.read_text())
    assert state["manifest"]["build"] == expected["build"], "VM belongs to a different build"
    state["captured_at"] = datetime.now(timezone.utc).isoformat()
    state["application_patches_applied"] = source.get("application_patches_applied", False)
    partial = folder / f"{args.engine}-{args.phase}-target-only-state.json"
    partial.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    if args.target_only:
        print(
            json.dumps({"engine": args.engine, "vm_evidence": str(partial), "nas_publication_checked": False})
        )
        return
    directory = (
        "/volume1/Releases/graphato-desktop" if args.engine == "jenkins" else "/leroy-graphato-releases"
    )
    program = (
        f"COMMIT={commit!r}\nDIRECTORY={directory!r}\nBUILD_TIMESTAMP={state['manifest']['build']['timestamp']!r}\n"
        + NAS_PROGRAM
    )
    if args.via_leroy:
        from nas_diagnostic import execute
        from watch_nas_graphato_via_leroy import JENKINS_ID

        guard = (
            "assert json.loads(subprocess.check_output(['docker','inspect','jenkins-parity'],text=True))[0]['Id']=="
            + repr(JENKINS_ID)
        )
        bounded_prefix = (
            "prefix=['docker','run','--rm','--pull=never','--read-only','--network','none',"
            "'--memory','128m','--cpus','0.5','--pids-limit','64','--mount',"
            "'type=bind,source='+DIRECTORY+',target='+DIRECTORY+',readonly',"
            "'--entrypoint','/usr/bin/env','leroy-job:nas-parity']"
        )
        program = program.replace(
            "assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()", guard
        ).replace("prefix=['docker','exec','leroy-nas-parity-docker-1']", bounded_prefix)
        program = program.replace(
            "print(json.dumps(rows))", "pathlib.Path('publication.json').write_text(json.dumps(rows))"
        )
        compile(program, "owned-publication-probe", "exec")
        diagnostic, _ = execute(
            "graphato-publication-" + args.engine + "-" + args.phase + "-" + commit[:12],
            program,
            timeout=180,
            artifacts=["publication.json"],
        )
        state["desktop_publication"] = json.loads(
            (diagnostic / "leroy-artifacts/probe/publication.json").read_text()
        )
    else:
        response = run_script("python3 - <<'PY'\n" + program + "PY\n", CREDENTIALS, sudo=True, timeout=90)
        if response.returncode:
            raise RuntimeError(response.stderr[-1000:])
        state["desktop_publication"] = json.loads(response.stdout)
    path = folder / f"{args.engine}-{args.phase}-state.json"
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    if args.via_leroy and args.candidate and args.engine == "leroy" and args.phase == "final":
        from collect_nas_graphato_archives import collect

        collect(args.candidate)
    print(
        json.dumps(
            {
                "engine": args.engine,
                "phase": args.phase,
                "status": state["receipt"]["status"],
                "commit": commit,
                "containers": state["containers"],
                "health_probes": state["health_probes"],
                "desktop_payload_verified": True,
            }
        )
    )


if __name__ == "__main__":
    main()
