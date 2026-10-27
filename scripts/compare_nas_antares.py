"""Run and record Antares on isolated Jenkins and Leroy, preserving both gates."""

import argparse
import json
import os
import tempfile
from contextlib import closing
from datetime import datetime, timezone

import httpx
from deploy_nas_parity import CREDENTIALS, LOCAL
from nas_ssh import ROOT, run_script

OUTPUT = ROOT / "test-results/nas-parity/antares"
STATE = OUTPUT / "pair.json"
COMMIT = "ab245279a2c5ba85dedef1180e7fd63b7f5b1398"

JENKINS = r"""
import base64,http.cookiejar,json,os,urllib.request,urllib.parse
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
headers={'Authorization':'Basic '+base64.b64encode(('admin:'+os.environ['PARITY_PASSWORD']).encode()).decode()}
def request(path,data=None):
 with opener.open(urllib.request.Request('http://127.0.0.1:8080'+path,headers=headers,data=data),timeout=60 if PHASE=='status' else 30) as response:
  return response.read(),dict(response.headers)
if PHASE=='configure':
 crumb=json.loads(request('/crumbIssuer/api/json')[0]);headers[crumb['crumbRequestField']]=crumb['crumb']
 headers['Content-Type']='application/xml'
 request('/createItem?name=antares-ci',open('/fixtures/antares-ci.xml','rb').read())
 print(json.dumps({'configured':True}))
elif PHASE in ('start','retry'):
 if PHASE=='start' and json.loads(request('/job/antares-ci/api/json?tree=lastBuild[number]')[0])['lastBuild']:
  raise RuntimeError('Comparison job already has a build; refusing an implicit rerun')
 crumb=json.loads(request('/crumbIssuer/api/json')[0]);headers[crumb['crumbRequestField']]=crumb['crumb']
 if PHASE=='retry':
  headers['Content-Type']='application/xml'
  request('/job/antares-ci/config.xml',open('/fixtures/antares-ci.xml','rb').read())
  del headers['Content-Type']
 endpoint='buildWithParameters' if b'ParametersDefinitionProperty' in open('/fixtures/antares-ci.xml','rb').read() else 'build'
 data,response=request('/job/antares-ci/'+endpoint,urllib.parse.urlencode(PARAMETERS).encode())
 print(json.dumps({'queue_url':response.get('Location'),'started':True}))
else:
 build=json.loads(request('/job/antares-ci/lastBuild/api/json?tree=number,result,building,timestamp,duration,actions[lastBuiltRevision[SHA1]]')[0])
 console=request('/job/antares-ci/lastBuild/consoleText')[0].decode(errors='replace')
 console=console.replace(os.environ['PARITY_PASSWORD'],'[REDACTED]')
 print(json.dumps({'build':build,'console':console}))
"""


def jenkins(phase, job="antares-ci", parameters=None):
    reviewed = json.loads((ROOT / "test-results/nas-parity/baseline.json").read_text())
    if job not in {item["pipeline"] for item in reviewed["pipelines"]}:
        raise ValueError("Only reviewed comparison jobs are available")
    script = (
        "PHASE="
        + repr(phase)
        + "\nPARAMETERS="
        + repr(parameters or {})
        + "\n"
        + JENKINS.replace("antares-ci", job)
    )
    return json.loads(jenkins_python(script, timeout=150 if phase == "status" else 60))


def jenkins_python(script, *, timeout=60):
    """Run a reviewed helper only inside the owned nested Jenkins container."""
    bridge = (
        "import subprocess\np=subprocess.run(['docker','exec','-i','leroy-nas-parity-docker-1','docker','exec','-i','jenkins-parity','python3','-'],input="
        + repr(script)
        + ",text=True,capture_output=True)\nprint(p.stdout)\nprint(p.stderr,file=__import__('sys').stderr)\nraise SystemExit(p.returncode)\n"
    )
    result = run_script("python3 - <<'PY'\n" + bridge + "PY\n", CREDENTIALS, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    return result.stdout


def client():
    api = httpx.Client(base_url="http://192.168.178.97:8088", headers={"X-Leroy-Request": "1"}, timeout=30)
    session = LOCAL / "admin-session.json"
    try:
        if session.exists():
            api.cookies.update(json.loads(session.read_text())["cookies"])
            response = api.get("/api/auth/me")
            if response.status_code == 200:
                return api
            if response.status_code != 401:
                response.raise_for_status()
            api.cookies.clear()
        result = api.post(
            "/api/auth/login",
            json={"username": "admin", "password": (LOCAL / "config/admin_password").read_text()},
            # Administrative password verification took 32 seconds under the
            # isolated VM's NAS pressure. Keep this separate from CI transport
            # and all ordinary status reads, which retain their existing limit.
            timeout=120,
        )
        result.raise_for_status()
        # Reuse the private test session instead of repeatedly hashing its password
        # during long builds. Atomic replacement also supports concurrent readers.
        descriptor, name = tempfile.mkstemp(prefix="admin-session-", dir=LOCAL)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump({"cookies": dict(api.cookies)}, stream)
            os.replace(name, session)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return api
    except BaseException:
        api.close()
        raise


def main():
    global OUTPUT, STATE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", choices=["initial", "aligned"], default="initial")
    parser.add_argument(
        "phase", choices=["start-jenkins", "retry-jenkins", "jenkins", "start-leroy", "leroy"]
    )
    args = parser.parse_args()
    if args.round == "aligned":
        OUTPUT = OUTPUT.parent / "aligned" / OUTPUT.name
        STATE = OUTPUT / "pair.json"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    state = (
        json.loads(STATE.read_text())
        if STATE.exists()
        else {"commit": COMMIT, "application_patches_applied": False, "complete": False}
    )
    if args.phase == "start-jenkins":
        if state.get("jenkins_start"):
            raise ValueError("Jenkins comparison already started")
        state["jenkins_start"] = jenkins("start")
    elif args.phase == "retry-jenkins":
        if not state.get("jenkins", {}).get("result") or state["jenkins"].get("building"):
            raise ValueError("Record the completed setup failure before retrying")
        state.setdefault("setup_attempts", []).append(state.pop("jenkins"))
        state["jenkins_start"] = jenkins("retry")
    elif args.phase == "jenkins":
        result = jenkins("status")
        (OUTPUT / f"jenkins-{result['build']['number']}-console.log").write_text(
            result["console"], encoding="utf-8"
        )
        (OUTPUT / "jenkins-console.log").write_text(result["console"], encoding="utf-8")
        (OUTPUT / "jenkins-build.json").write_text(json.dumps(result["build"], indent=2), encoding="utf-8")
        state["jenkins"] = result["build"]
        print(json.dumps(result["build"], indent=2))
        print(result["console"][-2000:])
    elif args.phase == "start-leroy":
        if state.get("leroy_run"):
            raise ValueError("Leroy comparison already started")
        if not state.get("jenkins", {}).get("result") or state["jenkins"].get("building"):
            raise ValueError("Record the completed Jenkins baseline first")
        result = run_script("docker exec leroy-nas-parity-docker-1 docker stop jenkins-parity\n", CREDENTIALS)
        if result.returncode:
            raise RuntimeError("Could not stop owned Jenkins comparison controller")
        with closing(client()) as api:
            pipelines = api.get("/api/pipelines").json()
            assert not any(p["enabled"] for p in pipelines), "Automatic triggers must remain disabled"
            response = api.post("/api/pipelines/antares-ci/runs", json={"parameters": {}, "commit": COMMIT})
            response.raise_for_status()
            state["leroy_run"] = response.json()["id"]
            print("Leroy run", state["leroy_run"])
    else:
        with closing(client()) as api:
            result = api.get("/api/runs/" + state["leroy_run"])
            result.raise_for_status()
            run = result.json()
            (OUTPUT / "leroy-run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
            for step in run["steps"]:
                offset = 0
                with (OUTPUT / ("leroy-" + step["id"] + ".log")).open("w", encoding="utf-8") as stream:
                    while offset < step["log_bytes"]:
                        response = api.get(
                            f"/api/runs/{run['id']}/logs/{step['id']}", params={"offset": offset}
                        )
                        response.raise_for_status()
                        log = response.json()
                        stream.write(log.get("text", ""))
                        if log.get("next_offset", offset) <= offset:
                            break
                        offset = log["next_offset"]
            state["leroy_status"] = run["status"]
            print(
                json.dumps(
                    {
                        "id": run["id"],
                        "status": run["status"],
                        "steps": [(s["id"], s["status"]) for s in run["steps"]],
                    },
                    indent=2,
                )
            )
    state["recorded_at"] = datetime.now(timezone.utc).isoformat()
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
