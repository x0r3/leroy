"""Check the four reproduced integration blockers before another full pipeline.

This diagnostic executes in the owned Jenkins container with a new disposable
database. It never counts as a full Jenkins/Leroy comparison.
"""

import json
import subprocess
import time

from nas_followup_support import inner, start_jenkins
from nas_gitea_target import idle
from nas_ssh import ROOT

PROGRAM = r"""
import json,os,pathlib,subprocess
root=pathlib.Path('/var/jenkins_home/workspace/antares-ci')
assert not subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()
subprocess.run(['git','fetch',SOURCE,COMMIT],cwd=root,check=True,capture_output=True)
subprocess.run(['git','checkout','--detach',COMMIT],cwd=root,check=True,capture_output=True)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==COMMIT
environment={**os.environ,'CI':'true','NODE_OPTIONS':'--max-old-space-size=2048',
 'TEST_DATABASE_URL':'postgres://antares:antares-test-password@antares-candidate-probe-db:5432/antares_test'}
commands=[['npm','run','lint'],['npm','run','typecheck'],
 ['node','node_modules/vitest/vitest.mjs','run','--config','vitest.integration.config.ts',
 'tests/integration/http-flows.test.ts','tests/integration/onboarding.test.ts',
 'tests/integration/npc-home-population.test.ts','tests/integration/visibility-events.test.ts']]
reports=[]
for command in commands:
 result=subprocess.run(command,cwd=root,env=environment,capture_output=True,text=True,timeout=600)
 reports.append({'command':command,'returncode':result.returncode,'console':result.stdout+result.stderr})
 if result.returncode:break
print(json.dumps(reports))
"""


def main():
    commit = subprocess.check_output(
        ["git", "-C", str(ROOT / ".sources/antares-nas-validation"), "rev-parse", "HEAD"], text=True
    ).strip()
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / commit
    staged = json.loads((folder / "staged.json").read_text())
    marker = folder / "focused-integration.json"
    assert not marker.exists(), "No implicit diagnostic rerun"
    idle()
    start_jenkins()
    name = "antares-candidate-probe-db"
    inner(
        "run",
        "-d",
        "--rm",
        "--name",
        name,
        "--label",
        "io.leroy.nas-parity=true",
        "--network",
        "leroy-jobs",
        "-e",
        "POSTGRES_DB=antares_test",
        "-e",
        "POSTGRES_USER=antares",
        "-e",
        "POSTGRES_PASSWORD=antares-test-password",
        "postgres:18.4-alpine3.24",
    )
    try:
        for _ in range(30):
            try:
                inner("exec", name, "pg_isready", "-U", "antares", "-d", "antares_test")
                break
            except RuntimeError:
                time.sleep(2)
        else:
            raise TimeoutError("Candidate probe database did not become ready")
        program = "COMMIT=" + repr(commit) + "\nSOURCE=" + repr(staged["source"]) + "\n" + PROGRAM
        reports = json.loads(inner("exec", "jenkins-parity", "python3", "-c", program, timeout=1800))
        for index, report in enumerate(reports):
            (folder / f"focused-integration-{index}.log").write_text(report.pop("console"), encoding="utf-8")
        result = {
            "commit": commit,
            "diagnostic_only": True,
            "commands": reports,
            "passed": len(reports) == 3 and all(row["returncode"] == 0 for row in reports),
        }
        marker.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
        assert result["passed"], "Inspect the focused diagnostic logs"
    finally:
        inner("stop", name, timeout=90)


if __name__ == "__main__":
    main()
