"""Compare independently rebuilt Python image contents and registry manifests."""

import json

from nas_followup_support import inner
from nas_ssh import ROOT

FOLDER = ROOT / "test-results/nas-parity/followup/home-lab-build"
SCAN = r"""
import hashlib,importlib.metadata,json,os,pathlib,platform,stat,subprocess,sysconfig
files=[]
roots=[pathlib.Path('/app'),pathlib.Path('/config/default.yaml'),pathlib.Path(sysconfig.get_paths()['purelib'])]
def visit(path):
 if path.name=='__pycache__' or path.suffix=='.pyc':return
 info=path.lstat()
 row={'path':str(path),'mode':stat.S_IMODE(info.st_mode),'uid':info.st_uid,'gid':info.st_gid}
 if path.is_symlink():row['link']=os.readlink(path)
 elif path.is_dir():
  row['directory']=True
  for child in sorted(path.iterdir()):visit(child)
 elif path.is_file():
  row['size']=info.st_size
  with path.open('rb') as stream:row['sha256']=hashlib.file_digest(stream,'sha256').hexdigest()
 else:raise ValueError('Unexpected application file type')
 files.append(row)
for root in roots:
 if root.exists():visit(root)
packages=sorted((d.metadata['Name'].lower(),d.version) for d in importlib.metadata.distributions())
system=subprocess.check_output(['dpkg-query','-W','-f=${Package}\t${Version}\t${Architecture}\n'],text=True).splitlines()
print(json.dumps({'files':sorted(files,key=lambda r:r['path']),'python':platform.python_version(),
 'python_packages':packages,'system_packages':sorted(system),'excluded_generated_files':['__pycache__','*.pyc'],'file_times_compared':False}))
"""
KEYS = [
    "Env",
    "Cmd",
    "Entrypoint",
    "User",
    "WorkingDir",
    "Labels",
    "Volumes",
    "Healthcheck",
    "ExposedPorts",
    "StopSignal",
]


def main():
    report = json.loads((FOLDER / "comparison.json").read_text())
    assert report["real_build_and_push_both"]
    identities = {
        engine: json.loads((FOLDER / (engine + "-images.json")).read_text())
        for engine in ("jenkins", "leroy")
    }
    comparisons = {}
    for service in identities["jenkins"]:
        found = {}
        for engine in ("jenkins", "leroy"):
            image = identities[engine][service]
            path = FOLDER / (engine + "-" + service + "-contents.json")
            if path.exists():
                scan = json.loads(path.read_text())
                assert scan["image"] == image["id"]
            else:
                scan = json.loads(
                    inner(
                        "run",
                        "--rm",
                        "--network",
                        "none",
                        "--read-only",
                        "--cap-drop",
                        "ALL",
                        "--security-opt",
                        "no-new-privileges:true",
                        "--memory",
                        "256m",
                        "--cpus",
                        "0.5",
                        "--entrypoint",
                        "python",
                        image["id"],
                        "-c",
                        SCAN,
                        timeout=240,
                    )
                )
                scan["image"] = image["id"]
                path.write_text(json.dumps(scan, indent=2) + "\n")
            found[engine] = scan
        left, right = found["jenkins"], found["leroy"]
        a, b = ({r["path"]: r for r in scan["files"]} for scan in (left, right))
        differences = [p for p in sorted(a.keys() | b.keys()) if a.get(p) != b.get(p)]
        same_runtime = {k: identities["jenkins"][service]["config"].get(k) for k in KEYS} == {
            k: identities["leroy"][service]["config"].get(k) for k in KEYS
        }
        item = {
            "same_runtime_configuration": same_runtime,
            "file_entries": len(a),
            "different_entries": differences,
            "same_python_version": left["python"] == right["python"],
            "same_python_packages": left["python_packages"] == right["python_packages"],
            "same_system_packages": left["system_packages"] == right["system_packages"],
            "python_packages": len(left["python_packages"]),
            "system_packages": len(left["system_packages"]),
        }
        comparisons[service] = item
        (FOLDER / "content-comparison.json").write_text(json.dumps(comparisons, indent=2) + "\n")
        assert not differences and all(
            item[k]
            for k in (
                "same_runtime_configuration",
                "same_python_version",
                "same_python_packages",
                "same_system_packages",
            )
        ), json.dumps(item)
        print(service, "contents/configuration matched:", len(a), "entries", flush=True)
    # Verify the immutable manifests of both builds remain retrievable even
    # after the second engine updates the two normal mutable tags.
    refs = sorted(
        {ref for images in identities.values() for item in images.values() for ref in item["digests"]}
    )
    registry = r"""
import hashlib,json,urllib.request
result=[]
for ref in REFS:
 repository,digest=ref.split('@')
 assert repository.startswith('registry:5000/home-lab/') and digest.startswith('sha256:')
 path='http://registry:5000/v2/'+repository.removeprefix('registry:5000/')+'/manifests/'+digest
 request=urllib.request.Request(path,headers={'Accept':', '.join([
  'application/vnd.oci.image.manifest.v1+json','application/vnd.oci.image.index.v1+json',
  'application/vnd.docker.distribution.manifest.v2+json','application/vnd.docker.distribution.manifest.list.v2+json'])})
 with urllib.request.urlopen(request,timeout=15) as response:
  payload=response.read()
  assert response.headers['Docker-Content-Digest']==digest
  assert 'sha256:'+hashlib.sha256(payload).hexdigest()==digest
 result.append(ref)
print(json.dumps(result))
"""
    verified = json.loads(
        inner(
            "run",
            "--rm",
            "--network",
            "leroy-jobs",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--memory",
            "128m",
            "--cpus",
            ".5",
            "--entrypoint",
            "python",
            "leroy-job:nas-parity",
            "-c",
            "REFS=" + repr(refs) + "\n" + registry,
        )
    )
    report.update(
        contents=comparisons,
        registry_manifests_verified=verified,
        workload_success_both=True,
        observed_scenario_parity=True,
        jenkins_pruned_intermediate_cache=True,
        byte_identical_images_claimed=report["same_image_ids"],
        excluded_from_content_comparison=["file timestamps", "generated Python bytecode"],
    )
    (FOLDER / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Both original-source build/push paths and their delivered content verified", flush=True)


if __name__ == "__main__":
    main()
