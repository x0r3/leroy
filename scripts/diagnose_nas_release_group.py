"""Run an unchanged original group from a fresh NAS baseline, as a diagnostic.

The existing CI definitions dispatch the work. No test instrumentation is added
to Graphato. This supporting evidence never replaces complete release acceptance.
"""

import argparse
import json
import subprocess
import threading
import time
from datetime import datetime, timezone

import compare_frozen_postdeploy_group as group
import compare_nas_full_release as release
import httpx
import nas_release_vm as vm
from nas_followup_support import inner, production_jobs
from nas_gitea_target import idle
from nas_measurement_guard import finish
from nas_ssh import ROOT
from observe_nas_release_jobs import PROGRAM as OWNED_JOB_PROBE

SQL_PROBE = r'''
import json,time
from sqlalchemy import text
from leroy.config import Settings
from leroy.db import connect
engine,_=connect(Settings.load().database_url)
at=time.perf_counter()
try:
 with engine.connect() as db:
  db.execute(text('SET TRANSACTION READ ONLY'))
  db.execute(text("SET LOCAL statement_timeout='3s'"))
  assert db.scalar(text('SELECT 1'))==1
 error=None
except Exception as e:error=type(e).__name__
print(json.dumps({'direct_query_with_connection_seconds':time.perf_counter()-at,'error':error}))
engine.dispose()
'''

# Keep SQL_PROBE as the retained old workload for isolated memory qualification.
# Periodic observation must not fork another application runtime in the API's
# hard memory budget. /health/ready already queries PostgreSQL through the API.
POSTGRES_PROBE = r'''
import json,subprocess,time
info=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-postgres-1'],text=True,timeout=3))[0]
assert info['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' and info['State']['Running']
at=time.perf_counter()
sql="SELECT json_build_object('value',1,'statement_elapsed_seconds',EXTRACT(EPOCH FROM clock_timestamp()-statement_timestamp()))"
r=subprocess.run(['docker','exec','-e','PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=3000',info['Id'],
 'psql','-XqAt','-U','leroy','-d','leroy','-c',sql],capture_output=True,text=True,timeout=6)
assert r.returncode==0,'Read-only database probe failed; output withheld'
value=json.loads(r.stdout);assert value.pop('value')==1
value.update(probe_location='postgres_container',read_only=True,postgres_client_process_seconds=time.perf_counter()-at)
print(json.dumps(value))
'''


def observe_control(folder, stopped):
    with httpx.Client(base_url="http://192.168.178.97:8088", timeout=5) as api:
        while not stopped.is_set():
            row = {"at": datetime.now(timezone.utc).isoformat()}
            for endpoint in ("/health/live", "/health/ready"):
                at = time.perf_counter()
                try:
                    response = api.get(endpoint)
                    row[endpoint] = {"seconds": time.perf_counter() - at, "status": response.status_code}
                except httpx.TransportError as error:
                    row[endpoint] = {"seconds": time.perf_counter() - at, "error": type(error).__name__}
            at = time.perf_counter()
            try:
                row["sql"] = json.loads(vm.remote(POSTGRES_PROBE, sudo=True, timeout=20))
            except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
                row["sql"] = {"wrapper_error": type(error).__name__}
            row["sql"]["ssh_and_docker_wrapper_seconds"] = time.perf_counter() - at
            with (folder / "control-latencies.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row) + "\n")
            stopped.wait(20)


def observe_owned_jobs(folder, stopped):
    """Retain bounded safe lease events before terminal workers are removed."""
    while not stopped.is_set():
        row = {"at": datetime.now(timezone.utc).isoformat()}
        try:
            row.update(json.loads(vm.remote(OWNED_JOB_PROBE, timeout=60)))
        except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
            row["observation_error"] = type(error).__name__
        with (folder / "owned-job-diagnostics.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        stopped.wait(20)


def collect_memory_evidence(folder, engine):
    """Keep optional observation failures from preventing terminal-job cleanup."""
    from nas_vm_memory_trace import collect_trace, summarize

    try:
        collect_trace(folder, engine)
        rows = [json.loads(line) for line in (folder / (engine + '-memory-samples.jsonl')).read_text().splitlines()]
        group.write(folder / (engine + '-memory-summary.json'), summarize(rows))
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        group.write(folder / (engine + '-memory-collection-error.json'),
                    {'error_type': type(error).__name__, 'memory_evidence_complete': False,
                     'original_ci_restarted': False})
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True)
    parser.add_argument("--engine", choices=("jenkins", "leroy"), required=True)
    parser.add_argument("--group", choices=("server-clippy", "server-test", "frontend", "dev-environments"), required=True)
    parser.add_argument("--resource-profile", choices=sorted(vm.MEMORY_PRESSURE_PROFILES), default="nas-6g-ssd-soft-ram-3584")
    parser.add_argument('--postgres-init', action='store_true', help='Use the qualified separate baseline override')
    parser.add_argument('--memory-trace', action='store_true', help='Retain bounded NAS-local host/QEMU/guest samples')
    parser.add_argument('--page-reporting-order', choices=(0, 4), type=int, default=4)
    parser.add_argument('--early-memory-pressure', action='store_true')
    parser.add_argument('--nas-local-capacity', action='store_true')
    parser.add_argument('--original-workload-qualification', action='store_true')
    parser.add_argument('--matching-ci-background', action='store_true')
    parser.add_argument('--separate-capacity-reference', action='store_true')
    args = parser.parse_args()
    if args.original_workload_qualification:
        assert args.matching_ci_background and not args.nas_local_capacity and not args.separate_capacity_reference
    release.configure_page_reporting(args.page_reporting_order)
    folder = (ROOT / args.folder).resolve()
    assert folder.is_relative_to(ROOT / "test-results/nas-parity/followup")
    folder.mkdir(parents=True, exist_ok=True)
    assert not (folder / "final-state.json").exists(), "Retain completed diagnostics"
    vm.configure(folder.name, args.resource_profile)
    release.POSTGRES_INIT = args.postgres_init
    release.SEPARATE_CAPACITY_REFERENCE = args.separate_capacity_reference
    if args.postgres_init:
        proof = group.read(ROOT / 'test-results/nas-parity/followup/offline-forensics-20261014/postgres-init-probe.json')
        assert proof['controlled_orphan_reproduction_passed']
    frozen = group.read(ROOT / "test-results/nas-parity/followup/candidates/graphato" / vm.COMMIT / "frozen-master.json")
    checkout = (ROOT / frozen["checkout"]).resolve()
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout, text=True).strip() == vm.COMMIT
    assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=checkout)
    suite = "web" if args.group == "dev-environments" else "quality"
    parameters = {"RELEASE_COMMIT": vm.COMMIT, "CHECK_GROUP": args.group}
    prepared = {"commit": vm.COMMIT, "parameters": parameters, "resource_profile": vm.RESOURCE_PROFILE,
                "scope": "Supporting original-group diagnostic, not full acceptance", "production_ready": False}
    if args.postgres_init:
        prepared['separate_test_baseline_postgres_init'] = True
    if args.memory_trace:
        prepared['nas_local_memory_trace'] = True
    if args.page_reporting_order != 4:
        prepared['guest_page_reporting_order'] = args.page_reporting_order
    if args.early_memory_pressure:
        prepared['early_memory_pressure'] = True
    if args.nas_local_capacity:
        prepared['nas_local_capacity'] = True
    if args.original_workload_qualification:
        prepared['original_workload_qualification'] = True
        prepared['synthetic_capacity_qualified'] = False
    if args.separate_capacity_reference:
        from nas_vm_capacity_reference import binding

        prepared['separate_capacity_reference'] = binding()
    if args.matching_ci_background:
        from nas_ci_background import capacity_proof

        prepared['matching_ci_background'] = True
        prepared['ci_slots'] = 2
        prepared['ci_capacity_alignment_proof_sha256'] = capacity_proof()
    if (folder / "prepared.json").exists():
        assert group.read(folder / "prepared.json") == prepared
    else:
        group.write(folder / "prepared.json", prepared)
    if not (folder/(args.engine+'-start.json')).exists():
        release.preflight_source_service(folder)
    group.restore, group.target = release.restore, release.target
    if args.memory_trace or args.page_reporting_order != 4 or args.early_memory_pressure or args.nas_local_capacity or args.original_workload_qualification:
        from nas_vm_memory_trace import start_trace

        def traced_restore(folder, engine, commit, baseline):
            release.restore(folder, engine, commit, baseline, page_reporting_order=args.page_reporting_order,
                            early_memory_pressure=args.early_memory_pressure, nas_local_capacity=args.nas_local_capacity,
                            original_workload_qualification=args.original_workload_qualification)
            if args.memory_trace and not (folder / (engine + '-memory-trace.json')).exists():
                start_trace(folder, engine)

        group.restore = traced_restore
    stop = threading.Event()
    threads = [threading.Thread(target=release.monitor, args=(folder, stop), daemon=True),
               threading.Thread(target=observe_control, args=(folder, stop), daemon=True)]
    if args.engine == "leroy":
        threads.append(threading.Thread(target=observe_owned_jobs, args=(folder, stop), daemon=True))
    for thread in threads:
        thread.start()
    collection_error = None
    if args.matching_ci_background:
        from nas_ci_background import prepare, record

        if not (folder / (args.engine + '-start.json')).exists():
            prepare(folder, args.engine)
    try:
        deadline = time.monotonic() + 9*3600
        while True:
            try:
                options = {"keep_private_jenkins": True} if args.matching_ci_background else {}
                group.execute_engine(folder, args.engine, vm.COMMIT, "graphato-postdeploy-" + suite,
                                     parameters, vm.SNAPSHOT, **options)
                break
            except (httpx.TransportError, httpx.HTTPStatusError) as error:
                assert (folder/(args.engine+'-start.json')).is_file(), 'Inspect an uncertain dispatch before resuming'
                assert time.monotonic()<deadline, 'Keep the original run; observation deadline reached'
                row={'at':group.timestamp(),'error_type':type(error).__name__,'original_ci_restarted':False}
                if isinstance(error,httpx.HTTPStatusError):
                    row['http_status']=error.response.status_code
                with (folder/'ci-observation-errors.jsonl').open('a') as stream:
                    stream.write(json.dumps(row)+'\n')
                print(json.dumps(row),flush=True)
                stop.wait(20)
    except (RuntimeError, subprocess.TimeoutExpired, OSError, AssertionError) as error:
        if not (folder / (args.engine + '-start.json')).exists():
            group.write(folder / 'preparation-error.json', {'type': type(error).__name__,
                        'original_ci_dispatched': False, 'preparation_complete': False})
            raise
        # Continue cleanup only when actual original CI terminal evidence exists.
        terminal = folder / ("leroy-run.json" if args.engine == "leroy" else "jenkins-terminal-observed.json")
        assert terminal.is_file(), "Keep observing the original run; no implicit cancellation or retry"
        if args.engine == "leroy":
            assert group.read(terminal)["status"] not in group.ACTIVE
        collection_error = type(error).__name__
        group.write(folder / "collection-error.json", {"type": collection_error, "original_run_restarted": False})
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=30)
        if args.memory_trace and (folder / (args.engine + '-memory-trace.json')).exists():
            collect_memory_evidence(folder, args.engine)
            # idle() below still rejects an active/uncertain original run.
    if args.matching_ci_background:
        record(folder, args.engine, 'after')
    idle()
    marker = group.read(folder / (args.engine + "-start.json"))
    finish(folder, args.engine, marker["production_guard_before"])
    if inner("inspect", "jenkins-parity", "--format", "{{.State.Running}}").strip() == "true":
        inner("stop", "--time", "120", "jenkins-parity", timeout=150)
    state = vm.state()
    if state["State"]["Running"]:
        vm.stop()
    group.write(folder / "final-state.json", {"at": group.timestamp(), "original_ci_terminal": True,
                "vm_running": vm.state()["State"]["Running"], "production_after": production_jobs(),
                "collection_error": collection_error, "full_release_acceptance": False, "production_ready": False})
    rows = [json.loads(line) for line in (folder / "control-latencies.jsonl").read_text().splitlines()]
    report = {"samples": len(rows), "api_timeouts": sum("error" in row[path] for row in rows for path in ("/health/live", "/health/ready")),
              "sql_wrapper_errors": sum("wrapper_error" in row["sql"] for row in rows),
              "direct_sql_errors": sum(bool(row["sql"].get("error")) for row in rows),
              "full_release_acceptance": False, "production_ready": False}
    group.write(folder / "control-summary.json", report)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
