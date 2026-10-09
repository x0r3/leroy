"""Diagnose the completed Jenkins unit failure with unchanged sources and a larger Node heap."""

import json
import time

from nas_followup_support import inner
from nas_ssh import ROOT

COMMIT = "88382cc055a84452f31317ad8087712a48428769"
FOLDER = ROOT / "test-results/nas-parity/followup/candidates/antares" / COMMIT / "memory-probe"
PROGRAM = r"""
import json,os,pathlib,subprocess,time
root=pathlib.Path('/var/jenkins_home/workspace/antares-ci')
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==COMMIT
assert subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=root,text=True).strip()==''
started=time.time()
result=subprocess.run(['npm','test'],cwd=root,env={**os.environ,'CI':'true','NODE_OPTIONS':'--max-old-space-size=2048'},text=True,capture_output=True,timeout=900)
print(json.dumps({'exit_code':result.returncode,'duration':time.time()-started,'console':result.stdout+result.stderr,'commit':COMMIT,'node_heap_mib':2048}))
"""


def main():
    FOLDER.mkdir(exist_ok=True)
    assert not (FOLDER / "started.json").exists()
    assert json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}")) is False
    old = json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .HostConfig.Memory}}"))
    assert old == 2 * 1024**3
    (FOLDER / "started.json").write_text(
        json.dumps(
            {
                "at": time.time(),
                "prior_container_memory": old,
                "container_memory": 3 * 1024**3,
                "source_unchanged": True,
                "full_pipeline_acceptance": False,
            }
        )
        + "\n"
    )
    inner("update", "--memory", "3g", "--memory-swap", "4g", "jenkins-parity")
    inner("start", "jenkins-parity")
    try:
        report = json.loads(
            inner(
                "exec",
                "jenkins-parity",
                "python3",
                "-c",
                "COMMIT=" + repr(COMMIT) + "\n" + PROGRAM,
                timeout=990,
            )
        )
        (FOLDER / "console.log").write_text(report.pop("console"), encoding="utf8")
        (FOLDER / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)
    finally:
        inner("stop", "jenkins-parity", timeout=240)
        inner("update", "--memory", "2g", "--memory-swap", "4g", "jenkins-parity")


if __name__ == "__main__":
    main()
