"""Confirm effective Jenkins plugins and application Python in the test instance."""

import json

from nas_ssh import ROOT, run_script

SCRIPT = r"""
import os,json,base64,urllib.request,subprocess
request=urllib.request.Request('http://127.0.0.1:8080/pluginManager/api/json?tree=plugins[shortName,version,active]',headers={'Authorization':'Basic '+base64.b64encode(('admin:'+os.environ['PARITY_PASSWORD']).encode()).decode()})
with urllib.request.urlopen(request,timeout=20) as response:
 result=json.load(response);result['core']=response.headers.get('X-Jenkins')
result['tools']={name:subprocess.check_output(command,text=True).strip() for name,command in {
 'worker_python':['python','--version'],'application_python':['python3','--version'],
 'node':['node','--version'],'npm':['npm','--version'],
}.items()}
print(json.dumps(result))
"""


def main():
    bridge = (
        'import subprocess\np=subprocess.run(["docker","exec","leroy-nas-parity-docker-1","docker","exec","jenkins-parity","python3","-c",'
        + repr(SCRIPT)
        + "],capture_output=True,text=True)\nprint(p.stdout)\nraise SystemExit(p.returncode)\n"
    )
    result = run_script("python3 - <<'PY'\n" + bridge + "PY\n", ROOT / ".local/nas-ssh.json", timeout=60)
    if result.returncode:
        raise RuntimeError("Isolated Jenkins alignment check is not ready")
    observed = json.loads(result.stdout)
    expected = json.loads((ROOT / "test-results/nas-parity/jenkins-versions.json").read_text())["production"]

    def versions(plugins):
        return {p["shortName"]: (p["version"], p["active"]) for p in plugins}

    observed["plugins_match_production"] = versions(observed["plugins"]) == versions(expected["plugins"])
    observed["core_matches_production"] = observed["core"] == expected["core"]
    observed["application_python_matches_worker"] = (
        observed["tools"]["application_python"] == observed["tools"]["worker_python"]
    )
    (ROOT / "test-results/nas-parity/jenkins-aligned-versions.json").write_text(
        json.dumps(observed, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in observed.items() if k != "plugins"}, indent=2))
    assert (
        observed["plugins_match_production"]
        and observed["core_matches_production"]
        and observed["application_python_matches_worker"]
    )


if __name__ == "__main__":
    main()
