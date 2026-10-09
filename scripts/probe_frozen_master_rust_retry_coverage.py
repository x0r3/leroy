"""Repeat one unchanged Rust assertion in fresh fixtures, without replacing the full-suite result."""

import argparse
import hashlib
import json
import re
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from nas_diagnostic import execute
from nas_operations_scope import require_operations_inputs
from nas_ssh import ROOT

TEST = "repositories::agent_worktrees::tests::story_integration_tests::story_locks_allow_independent_merges_and_exclude_shared_publication"

GUEST = r'''
import hashlib,importlib.util,json,os,pathlib,re,subprocess,tempfile
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
release=pathlib.Path('/opt/graphato/current').resolve(strict=True)
assert release.parent==pathlib.Path('/opt/graphato/releases')
manifest=json.loads((release/'manifest.json').read_text());assert manifest['commit']==COMMIT
with (release/'verification-source.tar.gz').open('rb') as stream:
 assert hashlib.file_digest(stream,'sha256').hexdigest()==manifest['files']['verification-source.tar.gz']
helper=release/'deployments/linux/host/postdeploy.py'
assert hashlib.sha256(helper.read_bytes()).hexdigest()==manifest['files']['deployments/linux/host/postdeploy.py']
spec=importlib.util.spec_from_file_location('original_postdeploy_diagnostic',helper)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
directory=module.STATE/'leroy-diagnostics'/('rust-retry-coverage-'+COMMIT[:12]+ATTEMPT_SUFFIX)
assert directory.resolve().is_relative_to(module.STATE.resolve()) and not directory.exists()
assert not (module.STATE/'fixture-state.json').exists()
directory.mkdir(parents=True,mode=0o700)
pointer=directory/'fixture-state.json'
samples=[];policies=[];projects=set();executor=None
with module.host_lock(), tempfile.TemporaryDirectory(prefix='source-',dir=directory) as source:
 source=pathlib.Path(source);module.source_extract(release/module.SOURCE_ARCHIVE,source)
 executor=module.Executor(source,directory/'preparation.log')
 ci=module.adapt_ci(source,release,manifest,executor)
 ci.STATE_ROOT=directory/'scratch'
 os.environ['CI_STATE_FILE']=str(pointer)
 normal_run=ci.run;normal_policy=ci.verification_policy
 def policy(config):
  config=normal_policy(config)
  server=config['services']['server-tests'];database=config['services']['postgres-test']
  assert server['mem_limit']==server['memswap_limit']=='6g' and server['cpus']==2
  assert server['environment']['RUST_TEST_THREADS']=='2'
  assert database['mem_limit']==database['memswap_limit']=='1536m' and database['cpus']==1
  policies.append({'server_memory':'6g','server_memory_and_swap':'6g','server_cpus':2,
                  'rust_test_threads':2,'database_memory':'1536m','database_memory_and_swap':'1536m','database_cpus':1})
  return config
 ci.verification_policy=policy
 selected=[0]
 def run(*args,**kwargs):
  args=list(args)
  if args[:2]==['docker','compose'] and '--project-name' in args:
   project=args[args.index('--project-name')+1]
   assert re.fullmatch(r'graphato-ci-check-[a-f0-9]{12}',project);projects.add(project)
   if args[-3:]==['server-tests','test','--timings']:
    args.pop() # This explicitly filtered probe uses standard libtest summaries.
    args.extend(['--lib',TEST,'--','--exact','--nocapture']);selected[0]+=1
  return normal_run(*args,**kwargs)
 ci.run=run
 try:
  for attempt in range(1,5):
   executor.log=directory/(str(attempt)+'.log')
   before=selected[0];exit_code=0
   try:ci.verify('full',actions=('test',))
   except subprocess.CalledProcessError as error:exit_code=error.returncode
   assert selected[0]==before+1,'Only one explicitly filtered original test invocation per sample'
   assert not pointer.exists() and not list((directory/'scratch').iterdir())
   data=executor.log.read_bytes();assert len(data)<module.MAX_LOG
   text=data.decode(errors='replace')
   summaries=re.findall(r'^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored;',text,re.MULTILINE)
   passed=sum(int(value[1]) for value in summaries);failed=sum(int(value[2]) for value in summaries)
   ignored=sum(int(value[3]) for value in summaries)
   assert passed+failed==1 and ignored==0,'A startup failure or incomplete sample is not a test result'
   assert (exit_code==0)==(passed==1)
   assertion='the overlapping PostgreSQL transactions must exercise a serialization retry'
   assert not failed or assertion in text,'A different failure requires separate investigation'
   samples.append({'attempt':attempt,'passed':passed==1,'exit_code':exit_code,
                   'retry_coverage_assertion_failed':bool(failed),'log_sha256':hashlib.sha256(data).hexdigest()})
   (directory/'samples.json').write_text(json.dumps(samples,indent=2)+'\n')
 finally:
  ci.cleanup(pointer)
  if executor.builder_started:executor.run('docker','buildx','stop',module.BUILDER,timeout=60)
 for project in projects:
  assert not executor.run('docker','ps','-aq','--filter','label=com.docker.compose.project='+project,capture=True).stdout.strip()
assert not pointer.exists()
print(json.dumps({'commit':COMMIT,'test':TEST,'samples':samples,'resource_policies':policies,
 'source_archive_sha256':manifest['files'][module.SOURCE_ARCHIVE],
 'completed_samples':len(samples),'cleanup_complete':True,'application_source_changed':False,
 'application_settings_changed':False,'full_suite_result_replaced':False,
 'test_selection':'One original case; other libtests are filtered, not accepted',
 'scope':'Supporting variance diagnosis; four bounded fresh PostgreSQL fixtures with original limits and two Rust test threads'}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--attempt", choices=["initial", "adapter-fixed"], default="initial")
    args = parser.parse_args()
    assert re.fullmatch(r"[a-f0-9]{40}", args.commit)
    base = ROOT / "test-results/nas-parity/followup/candidates/graphato" / args.commit
    require_operations_inputs(base, args.commit, infrastructure_only=True)
    analysis = json.loads((base / "scenarios/root-private-existing-host/analysis.json").read_text())
    details = analysis["suites"]["quality"]["test_details"]
    assert details["jenkins"]["rust"]["failed"] == 0
    assert details["leroy"]["rust"]["failed_tests"] == [TEST]
    name = "frozen-master-rust-coverage-" + args.commit[:12]
    suffix = "" if args.attempt == "initial" else "-adapter-fixed"
    if suffix:
        original = ROOT / "test-results/nas-parity/followup" / name
        assert json.loads((original / "run.json").read_text())["status"] == "failed"
        proof = json.loads((original / "startup-failure-analysis.json").read_text())
        assert proof["helper_argument_binding_failed"] and proof["application_tests_started"] is False
    name += suffix
    folder = ROOT / "test-results/nas-parity/followup" / name
    assert not folder.exists(), "Preserve the first supporting probe; no implicit repetition"
    guest = "COMMIT=" + repr(args.commit) + "\nTEST=" + repr(TEST) + "\nATTEMPT_SUFFIX=" + repr(suffix) + "\n" + GUEST
    compile(guest, "original Rust case diagnostic", "exec")
    program = ("import json,pathlib,subprocess\nfrom leroy.actions import required,ssh_args\n"
               "command=ssh_args('graphato-vm','root',12225,required('BOOTSTRAP_KEY'),required('KNOWN_HOSTS'))\n"
               "result=subprocess.run([*command,'python3 -B -'],input=" + repr(guest) +
               ",text=True,capture_output=True,timeout=900)\n"
               "if result.returncode:\n"
               " import hashlib,re\n"
               " failure={'guest_exit_code':result.returncode,'stdout_sha256':hashlib.sha256(result.stdout.encode()).hexdigest(),"
               "'stderr_sha256':hashlib.sha256(result.stderr.encode()).hexdigest(),"
               "'exception_types':re.findall(r'^([A-Za-z]+Error):',result.stderr,re.MULTILINE)}\n"
               " pathlib.Path('failure.json').write_text(json.dumps(failure,indent=2)+'\\n')\n"
               " print('Supporting fixture probe failed',result.returncode,flush=True)\n"
               " raise SystemExit(1)\n"
               "value=json.loads(result.stdout)\n"
               "pathlib.Path('result.json').write_text(json.dumps(value,indent=2)+'\\n')\n"
               "print(json.dumps({'completed_samples':value['completed_samples'],"
               "'passed_samples':sum(row['passed'] for row in value['samples'])}),flush=True)\n"
               "raise SystemExit(0 if all(row['passed'] for row in value['samples']) else 1)\n")
    compile(program, "NAS Rust case dispatcher", "exec")
    with closing(client()) as api:
        previous = next(row["spec"] for row in api.get("/api/pipelines").json()
                        if row["id"] == "leroy-nas-diagnostics")
    try:
        try:
            execute(name, program, secrets=("graphato-bootstrap",), timeout=960,
                    artifacts=("result.json", "failure.json"), profile="graphato")
        except AssertionError:
            assert (folder / "run.json").is_file(), "Inspect retained startup failure"
            assert json.loads((folder / "run.json").read_text())["status"] == "failed"
            assert (folder / "leroy-artifacts/probe/result.json").is_file(), "No completed supporting samples"
    finally:
        with closing(client()) as api:
            api.put("/api/pipelines/leroy-nas-diagnostics", json=previous).raise_for_status()
            definitions = api.get("/api/pipelines").json()
            assert next(row["spec"] for row in definitions if row["id"] == "leroy-nas-diagnostics") == previous
            assert not any(row["enabled"] for row in definitions)
    path = folder / "leroy-artifacts/probe/result.json"
    result = json.loads(path.read_text())
    assert result["commit"] == args.commit and result["completed_samples"] == 4 and result["cleanup_complete"]
    record = {"at": datetime.now(timezone.utc).isoformat(), "supporting_probe_completed": True,
              "test_outcomes_varied": len({row["passed"] for row in result["samples"]}) > 1,
              "result": result, "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "run_evidence": (folder / "run.json").relative_to(ROOT).as_posix(),
              "previous_diagnostic_definition_restored": True, "ci_dispatcher_on_nas": True,
              "attempt": args.attempt, "earlier_startup_failure_retained": bool(suffix),
              "production_modified": False, "full_suite_acceptance_replaced": False}
    destination = base / "scenarios/root-private-existing-host/rust-retry-coverage-probe.json"
    assert not destination.exists()
    destination.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"supporting_probe_completed": True, "test_outcomes_varied": record["test_outcomes_varied"],
                      "passed_samples": sum(row["passed"] for row in result["samples"])}), flush=True)


if __name__ == "__main__":
    main()
