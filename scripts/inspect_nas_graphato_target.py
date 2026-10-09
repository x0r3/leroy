"""Record read-only progress of the exact candidate on the isolated target VM."""

import argparse
import json
from datetime import datetime, timezone

from nas_candidate_paths import comparison_source
from prepare_nas_vm import guest

PROGRAM = r"""
import json,pathlib,re,time
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
release=pathlib.Path('/opt/graphato/current').resolve(strict=True)
assert release.parent==pathlib.Path('/opt/graphato/releases')
manifest=json.loads((release/'manifest.json').read_text())
assert manifest['commit']==CANDIDATE
root=pathlib.Path('/var/lib/graphato-host/postdeploy/results')/CANDIDATE
rows={}
for path in root.glob('*/result.json'):
 data=json.loads(path.read_text())
 assert data['commit']==CANDIDATE and data['buildTimestamp']==manifest['build']['timestamp']
 row={key:data.get(key) for key in ('commit','passed','completedAt','cleanupComplete','checks','cancelled','reused','buildTimestamp')}
 row['elapsed_seconds']=round((data['completedAt'] or time.time())-data['startedAt'])
 row['logs']=[{'name':p.name,'bytes':p.stat().st_size,'age_seconds':round(time.time()-p.stat().st_mtime)} for p in path.parent.glob('*.log')]
 latest=max(path.parent.glob('*.log'),key=lambda p:p.stat().st_mtime,default=None)
 if latest:
  plain=re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',latest.read_text(errors='replace'))
  progress=[line.strip()[:180] for line in plain.splitlines() if re.match(r'^\s*(Compiling |Checking |Finished |Test Files\s|Tests\s|Duration\s|test result:)',line)]
  row['build_progress']={'log':latest.name,'progress_lines':len(progress),'latest':progress[-3:]}
 rust=path.parent/'server-test.log'
 if rust.exists():
  counts={'expected':0,'ok':0,'ignored':0,'failed':[]}
  for line in rust.read_text().splitlines():
   if not line.startswith('{'):continue
   try:event=json.loads(line)
   except ValueError:continue
   if event.get('type')=='suite' and event.get('event')=='started':counts['expected']+=event['test_count']
   if event.get('type')=='test':
    if event.get('event') in ('ok','ignored'):counts[event['event']]+=1
    if event.get('event')=='failed':counts['failed'].append(event['name'])
  row['rust']=counts
 rows[path.parent.name]=row
print(json.dumps(rows))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", choices=["jenkins", "leroy"])
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args()
    _, folder = comparison_source("graphato-ci", args.candidate)
    rows = json.loads(guest("sudo python3 -", "CANDIDATE=" + repr(args.candidate) + "\n" + PROGRAM, timeout=45))
    record = {"at": datetime.now(timezone.utc).isoformat(), "engine": args.engine, "suites": rows}
    with (folder.parent / (args.engine + "-target-observations.jsonl")).open("a") as output:
        output.write(json.dumps(record) + "\n")
    for suite, row in rows.items():
        print(
            json.dumps(
                {
                    "suite": suite,
                    "completed": row["completedAt"] is not None,
                    "passed": row["passed"],
                    "elapsed_seconds": row["elapsed_seconds"],
                    "passed_checks": sum(v["passed"] for v in row["checks"].values()),
                    "failed_checks": {k: v for k, v in row["checks"].items() if not v["passed"]},
                    "latest_logs": sorted(row["logs"], key=lambda v: v["age_seconds"])[:2],
                    **({"build_progress": row["build_progress"]} if suite == "quality" and "build_progress" in row else {}),
                    **({"rust": row["rust"]} if "rust" in row else {}),
                }
            )
        )


if __name__ == "__main__":
    main()
