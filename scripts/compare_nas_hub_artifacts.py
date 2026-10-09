"""Compare application content, permissions and runtime configuration of both images."""

import json

from compare_nas_antares import jenkins_python
from nas_ssh import ROOT

SCAN = r"""const fs=require('fs'),path=require('path'),crypto=require('crypto');
const records=[];
function visit(name){
 const s=fs.lstatSync(name);const r={path:name.slice(5),mode:s.mode&0o777,uid:s.uid,gid:s.gid};
 if(s.isSymbolicLink()){r.link=fs.readlinkSync(name);}
 else if(s.isDirectory()){r.directory=true;for(const entry of fs.readdirSync(name).sort())visit(path.join(name,entry));}
 else if(s.isFile()){r.sha256=crypto.createHash('sha256').update(fs.readFileSync(name)).digest('hex');r.size=s.size;}
 else throw new Error('Unexpected application file type');
 records.push(r);
}
visit('/app');records.sort((a,b)=>a.path.localeCompare(b.path));process.stdout.write(JSON.stringify(records));
"""


def main():
    folder = ROOT / "test-results/nas-parity/aligned/nikicas-hub-ci"
    collected = {}
    for engine in ("jenkins", "leroy"):
        identity = json.loads((folder / (engine + "-image.json")).read_text())["id"]
        script = """import json,subprocess
image=json.loads(subprocess.check_output(['docker','image','inspect',IMAGE]))[0]
files=json.loads(subprocess.check_output(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','256m','--cpus','0.5','--entrypoint','node',IMAGE,'-e',SCAN]))
keys=['Env','Cmd','Entrypoint','User','WorkingDir','Labels','Volumes','Healthcheck','ExposedPorts','StopSignal']
print(json.dumps({'image':IMAGE,'configuration':{k:image['Config'].get(k) for k in keys},'files':files}))
"""
        result = json.loads(
            jenkins_python("IMAGE=" + repr(identity) + "\nSCAN=" + repr(SCAN) + "\n" + script)
        )
        (folder / (engine + "-application-files.json")).write_text(json.dumps(result, indent=2) + "\n")
        collected[engine] = result
    left, right = collected["jenkins"], collected["leroy"]
    a, b = ({f["path"]: f for f in item["files"]} for item in (left, right))
    differences = [name for name in sorted(a.keys() | b.keys()) if a.get(name) != b.get(name)]
    comparison = {
        "jenkins_image": left["image"],
        "leroy_image": right["image"],
        "same_runtime_configuration": left["configuration"] == right["configuration"],
        "application_entries": len(a),
        "different_application_entries": differences,
        "same_application_contents_and_permissions": not differences,
        "image_timestamps_and_layer_metadata_excluded": True,
    }
    (folder / "artifact-comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
    print(json.dumps({**comparison, "different_application_entries": differences[:20]}, indent=2))


if __name__ == "__main__":
    main()
