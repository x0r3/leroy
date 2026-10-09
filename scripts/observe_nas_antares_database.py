"""Read PostgreSQL wait states during one already running Antares browser phase."""

import argparse
import json
import re
import time
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from nas_ssh import ROOT, run_script

QUERY = """
SELECT coalesce(json_agg(activity), '[]'::json) FROM (
  SELECT pid, state, wait_event_type, wait_event,
         round(extract(epoch FROM clock_timestamp() - query_start)::numeric, 3) AS query_seconds,
         round(extract(epoch FROM clock_timestamp() - xact_start)::numeric, 3) AS transaction_seconds,
         pg_blocking_pids(pid) AS blockers, md5(query) AS query_hash,
         split_part(ltrim(query), ' ', 1) AS operation
  FROM pg_stat_activity
  WHERE datname = current_database() AND pid <> pg_backend_pid()
    AND state <> 'idle'
  ORDER BY pid
) activity
"""

PROGRAM = r"""
import json,pathlib,subprocess,time,datetime
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
prefix=['docker','exec','leroy-nas-parity-docker-1','docker']
info=json.loads(subprocess.check_output([*prefix,'inspect',NAME],text=True,timeout=15))[0]
assert info['Name']=='/'+NAME and info['Config']['Labels']['io.leroy.run']==RUN_ID
assert info['Config']['Image']=='postgres:18.4-alpine3.24'
samples=[];deadline=time.monotonic()+180
for index in range(60):
 if time.monotonic()>=deadline:break
 started=time.monotonic()
 result=subprocess.run([*prefix,'exec','-e','PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=2000',
                        NAME,'psql','-X','-qAt','-U','antares','-d','antares_test','-c',QUERY],
                       text=True,capture_output=True,timeout=15)
 sample={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'returncode':result.returncode}
 if result.returncode==0:sample['activity']=json.loads(result.stdout)
 else:sample['error']=result.stderr[-500:]
 samples.append(sample)
 if result.returncode:break
 time.sleep(max(0,3-(time.monotonic()-started)))
logs=subprocess.run([*prefix,'logs','--since',SINCE,NAME],text=True,capture_output=True,timeout=15)
messages=[line for line in (logs.stdout+logs.stderr).splitlines()
          if any(word in line for word in ('ERROR:', 'FATAL:', 'deadlock detected', 'canceling statement'))]
print(json.dumps({'samples':samples,'postgres_errors':messages,'logs_returncode':logs.returncode}))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    run_id = parser.parse_args().run
    assert re.fullmatch("[a-f0-9]{32}", run_id)
    deadline = time.monotonic() + 2400
    with closing(client()) as api:
        while time.monotonic() < deadline:
            response = api.get("/api/runs/" + run_id)
            response.raise_for_status()
            run = response.json()
            assert run["pipeline_id"] == "antares-ci"
            step = next(step for step in run["steps"] if step["id"] == "browsers")
            if step["status"] == "running":
                break
            assert run["status"] in ("queued", "running"), "No active browser phase to observe"
            time.sleep(15)
        else:
            raise TimeoutError("Browser phase did not begin; no database setting changed")
    name = "leroy-antares-" + run_id
    database = next(step for step in run["steps"] if step["id"] == "postgres")
    assert database["status"] == "succeeded" and database["outputs"]["database_container"] == name
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / run["commit"]
    assert folder.is_dir() and re.fullmatch("[a-f0-9]{40}", run["commit"])
    target = folder / ("leroy-" + run_id + "-database-waits.json")
    assert not target.exists(), "Retain previous observations"
    values = {"RUN_ID": run_id, "NAME": name, "SINCE": step["started_at"], "QUERY": QUERY}
    program = "\n".join(key + "=" + repr(value) for key, value in values.items()) + "\n" + PROGRAM
    compile(program, "read-only-postgresql-observer", "exec")
    print("Sampling PostgreSQL wait states during browser phase:", run_id, flush=True)
    response = run_script(
        "python3 - <<'PY'\n" + program + "\nPY\n", ROOT / ".local/nas-ssh.json",
        sudo=True, timeout=240,
    )
    if response.returncode:
        raise RuntimeError(response.stderr[-1500:])
    report = json.loads(response.stdout)
    report.update(run=run_id, candidate=run["commit"], read_only=True, captured_at=datetime.now(timezone.utc).isoformat())
    target.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"samples": len(report["samples"]), "postgres_errors": report["postgres_errors"]}), flush=True)


if __name__ == "__main__":
    main()
