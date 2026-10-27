"""One of two human-approved four-hour NAS full-release comparison windows.

The two engine windows have separate NAS recovery journals. The original CI
definitions, sources, tests and deadlines remain unchanged. Every pause is
followed by recovery, including dispatch, collection and transport failures.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

import nas_release_vm as vm
from diagnose_nas_release_group import observe_control, observe_owned_jobs
from nas_followup_support import inner, production_jobs
from nas_gitea_target import idle
from nas_ssh import ROOT, upload_file

ROUND = 'full-release-controller512-20261013'
LEGACY_ROUND = ROUND
RECONCILE_ROUND = 'full-release-reconcile8g-20261014'
FOLLOWUP = ROOT / 'test-results/nas-parity/followup'
SERVICES = ('paperless', 'sonarr', 'radarr', 'sabnzbd', 'plex',
            'yt-downloader-service', 'mail-ingest-service')
PROFILE = 'nas-10g-ssd-soft-ram-3584'


def configure_comparison(round_name):
    global ROUND, PROFILE
    assert round_name in {LEGACY_ROUND, RECONCILE_ROUND}
    ROUND = round_name
    PROFILE = 'nas-8g-ssd-soft-ram-3584' if ROUND == RECONCILE_ROUND else 'nas-10g-ssd-soft-ram-3584'


def window_name(engine):
    assert engine in {'leroy', 'jenkins'}
    return ('resource-window-reconcile8g-' + engine + '-20261014' if ROUND == RECONCILE_ROUND else
            'resource-window-full-' + engine + '-20261013')


def qualification_round(engine):
    assert ROUND == RECONCILE_ROUND and engine in {'leroy', 'jenkins'}
    return ROUND + '-rust-' + engine


def require_window_approval():
    if ROUND != RECONCILE_ROUND:
        return
    path = FOLLOWUP / 'reconcile8g-window-plan-20261014/approval.json'
    assert path.is_file(), 'The two previous windows are closed; new explicit user approval is required'
    approval = read(path)
    assert approval['user_approved'] is True and approval['comparison_round'] == RECONCILE_ROUND
    assert approval['maximum_window_seconds'] == 14400
    assert set(approval['engines']) == {'leroy', 'jenkins'}
    assert set(approval['services']) == set(SERVICES)


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def action(remote, name, run=None, *, operation_timeout=None):
    args = ['python3', remote + '/guard.py', name]
    if run:
        args += ['--run', run]
    limit = 1000 if name == 'pause' else 400
    if operation_timeout is not None:
        assert name in {'restore', 'status'} and type(operation_timeout) is int
        assert 1 <= operation_timeout <= limit, 'A caller may only reduce the existing recovery RPC limit'
        limit = operation_timeout
    program = ('import subprocess\nr=subprocess.run(' + repr(args) +
               ',capture_output=True,text=True,timeout=' + str(limit) + ')\n'
               "assert r.returncode==0,'Recovery operation failed; inspect protected journal'\nprint(r.stdout)")
    return json.loads(vm.remote(program, sudo=True, timeout=limit + 20))


def infrastructure():
    program = r'''
import hashlib,json,pathlib,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert root.resolve()==root and (root/'.leroy-owned').is_file()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
rows={};states={};controller_memory=None
for service in ('postgres','controller','runner','docker'):
 info=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-'+service+'-1'],text=True,timeout=15))[0]
 assert info['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
 rows[service]={'image':info['Image'],'environment_sha256':digest(sorted(info['Config']['Env'])),
  'command_sha256':digest({key:info['Config'].get(key) for key in ('Cmd','Entrypoint','WorkingDir','User')}),
  'resources':{key:info['HostConfig'][key] for key in ('Memory','MemorySwap','NanoCpus','MemoryReservation','CgroupParent','BlkioDeviceReadBps','BlkioDeviceWriteBps')},
  'logging':info['HostConfig']['LogConfig'],
  'mounts':sorted([{key:m[key] for key in ('Type','Source','Destination','RW')} for m in info['Mounts']],key=lambda m:(m['Destination'],m['Source'],m['Type'],m['RW']))}
 states[service]={'id':info['Id'],'restart_count':info['RestartCount'],'pid':info['State']['Pid'],
  'running':info['State']['Running'],'health':info['State'].get('Health',{}).get('Status'),
  'started_at':info['State']['StartedAt'],'oom_killed':info['State']['OOMKilled']}
 assert info['State']['Running']
 if service=='controller':
  unified=[line[3:] for line in pathlib.Path('/proc',str(info['State']['Pid']),'cgroup').read_text().splitlines() if line.startswith('0::')]
  assert len(unified)==1
  relative=pathlib.PurePosixPath(unified[0]);assert relative.is_absolute() and '..' not in relative.parts
  assert relative.name in {info['Id'],'docker-'+info['Id']+'.scope'}
  directory=pathlib.Path('/sys/fs/cgroup').joinpath(*relative.parts[1:]);assert directory.resolve(strict=True)==directory
  controller_memory={name:(int((directory/name).read_text()) if name!='memory.events' else
   {key:int(value) for key,value in (line.split() for line in (directory/name).read_text().splitlines())})
   for name in ('memory.current','memory.max','memory.swap.current','memory.events')}
assert rows['controller']['resources']['Memory']==536870912
assert rows['controller']['resources']['MemorySwap']==536870912
sql="select json_build_object('fsync',current_setting('fsync'),'synchronous_commit',current_setting('synchronous_commit'),'full_page_writes',current_setting('full_page_writes'))"
durability=json.loads(subprocess.check_output(['docker','exec','-e','PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=15000','leroy-nas-parity-postgres-1','psql','-XqAt','-U','leroy','-d','leroy','-c',sql],text=True,timeout=30))
assert durability=={'fsync':'on','synchronous_commit':'on','full_page_writes':'on'}
paths=['compose.yaml','compose.override.yaml','config/leroy.toml','config/runner.toml','config/controller.env']
print(json.dumps({'services':rows,'states':states,'controller_memory':controller_memory,'postgres_durability':durability,
 'configuration_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in paths}}))
'''
    value = json.loads(vm.remote(program, sudo=True, timeout=90))
    value['comparison_driver_sha256'] = {name: hashlib.sha256((ROOT / 'scripts' / name).read_bytes()).hexdigest()
        for name in ('compare_nas_full_release.py', 'compare_frozen_release_cpu_eight.py', 'nas_vm_page_reporting.py',
                     'nas_vm_cache.py', 'nas_vm_memory_pressure.py', 'nas_release_vm.py',
                     'diagnose_nas_release_group.py', 'run_nas_full_release_window.py', 'nas_resource_window_guard.py',
                     'compare_frozen_postdeploy_group.py', 'nas_vm_memory_trace.py')}
    value['at'] = datetime.now(timezone.utc).isoformat()
    return value


def prepare(folder, remote, engine):
    require_window_approval()
    idle()
    assert not vm.state()['State']['Running']
    assert inner('inspect', 'jenkins-parity', '--format', '{{.State.Running}}').strip() == 'false'
    production = production_jobs()
    assert not production['active_builds'] and production['older_concurrent_build_history_verified']
    before = infrastructure()
    if ROUND == RECONCILE_ROUND:
        qualified = read(FOLLOWUP / 'controller-reconcile-locks-20261014/postgres-validation.json')
        assert qualified['all_passed'] and qualified['postgres_tests'] == 34 and qualified['skipped'] == 0
        assert before['services']['controller']['image'] == qualified['candidate_image']
        assert hashlib.sha256((ROOT / 'src/leroy/engine.py').read_bytes()).hexdigest() == qualified['engine_sha256']
    write(folder / 'infrastructure-before.json', before)
    if engine == 'jenkins':
        previous = FOLLOWUP / window_name('leroy')
        assert read(previous / 'window-result.json')['all_seven_original_services_restored_healthy']
        first = read(previous / 'infrastructure-before.json')
        assert all(first[key] == before[key] for key in
                   ('services', 'postgres_durability', 'configuration_sha256', 'comparison_driver_sha256'))
    program = 'NAMES=' + repr(SERVICES) + '\n' + r'''
import json,subprocess,pathlib,shutil
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
infos=json.loads(subprocess.check_output(['docker','inspect',*NAMES],text=True,timeout=20))
assert len(infos)==7
rows=[]
for name,info in zip(NAMES,infos):
 assert info['Name']=='/'+name and info['State']['Running']
 assert info['State'].get('Health',{}).get('Status') in (None,'healthy')
 rows.append({'name':name,'id':info['Id']})
assert shutil.disk_usage('/overlay').free>=MINIMUM_SSD_FREE_GIB*1024**3
print(json.dumps({'containers':rows,'disk_free_bytes':shutil.disk_usage('/overlay').free}))
'''
    reviewed = json.loads(vm.remote('MINIMUM_SSD_FREE_GIB=' + repr(70 if ROUND == RECONCILE_ROUND else 40) + '\n' + program,
                                   sudo=True, timeout=40))
    plan = {'user_approved': True, 'maximum_window_seconds': 14400, 'graceful_stop_seconds': 120,
            'comparison_round': ROUND, 'engine': engine, 'containers': reviewed['containers'],
            'production_counters': {name: row['number'] for name, row in production['jobs'].items()},
            'approved_scope': 'Two separate four-hour windows; restore the seven services after each window'}
    if ROUND == RECONCILE_ROUND:
        plan['rust_qualification_round'] = qualification_round(engine)
    write(folder / 'plan.json', plan)
    write(folder / 'production-before.json', production)
    staging = remote + '-input'
    program = 'import pathlib\n'
    for location in (remote, staging):
        program += ('p=pathlib.Path(' + repr(location) + ')\nassert not p.exists()\n'
                    "assert p.parent.resolve()==p.parent and (p.parent/'.leroy-owned').is_file()\np.mkdir(mode=0o700)\n")
    vm.remote(program, timeout=40)
    for name, source in (('plan.json', folder / 'plan.json'), ('guard.py', ROOT / 'scripts/nas_resource_window_guard.py')):
        upload_file(source, staging + '/' + name, vm.CREDENTIALS, timeout=60)
    program = ('import pathlib,shutil,os,subprocess,json,hashlib\np=pathlib.Path(' + repr(remote) +
               ');s=pathlib.Path(' + repr(staging) + ')\n'
               "os.chown(p,0,0);p.chmod(0o700)\n"
               "for name in ('plan.json','guard.py'):\n shutil.copyfile(s/name,p/name);os.chown(p/name,0,0);(p/name).chmod(0o600)\n"
               "print(hashlib.sha256((p/'guard.py').read_bytes()).hexdigest())\n")
    assert vm.remote(program, sudo=True, timeout=30).strip() == hashlib.sha256(
        (ROOT / 'scripts/nas_resource_window_guard.py').read_bytes()).hexdigest()
    state = action(remote, 'prepare')
    write(folder / 'prepared-window.json', state)
    unit = folder.name
    program = ('import subprocess,json\nargs=' + repr(['systemd-run', '--unit=' + unit,
        '--property=Restart=on-failure', '--property=RestartSec=10', '--property=StandardOutput=null',
        '--property=StandardError=null', '/usr/bin/python3', remote + '/guard.py', 'watch']) + '\n'
        "r=subprocess.run(args,capture_output=True,text=True,timeout=20)\nassert r.returncode==0,'Watchdog preparation failed; no services stopped'\n"
        'assert subprocess.check_output(' + repr(['systemctl', 'is-active', unit + '.service']) +
        ",text=True,timeout=10).strip()=='active'\nprint(json.dumps({'watchdog_active':True}))")
    write(folder / 'watchdog.json', json.loads(vm.remote(program, sudo=True, timeout=40)))


def verify_recovery(folder, remote):
    program = ('P=' + repr(remote) + '\n' + r'''
import runpy,json,time
module=runpy.run_path(P+'/guard.py');state=module['read']()
assert state['phase']=='restored' and len(state['containers'])==7
rows=[]
for row in state['containers']:
 assert row['phase']=='restored'
 info=module['reviewed'](row)
 rows.append({'name':row['name'],'id':info['Id'],'image':info['Image'],
  'configuration_sha256':module['fingerprint'](info),'running':info['State']['Running'],
  'pid':info['State']['Pid'],'oom_killed':info['State']['OOMKilled'],
  'health':info['State'].get('Health',{}).get('Status'),'restart_count':info['RestartCount']})
print(json.dumps({'at_epoch':time.time(),'containers':rows}))
''')
    samples = []
    deadline = time.monotonic() + 360
    while time.monotonic() < deadline:
        value = json.loads(vm.remote(program, sudo=True, timeout=40))
        samples.append(value)
        write(folder / 'recovery-observations.json', samples)
        healthy = all(r['running'] and not r['oom_killed'] and r['health'] in (None, 'healthy')
                      for r in value['containers'])
        if healthy and len(samples) >= 3 and all(s['containers'] == value['containers'] for s in samples[-3:]):
            write(folder / 'recovery-verification.json', value)
            return value
        time.sleep(20)
    raise RuntimeError('Service health or stability verification incomplete; retain recovery observations')


def require_rust_evidence(case, engine):
    from compare_frozen_postdeploy_group import original_group_evidence

    final = read(case / 'final-state.json')
    assert final['original_ci_terminal'] and not final['vm_running'] and final['collection_error'] is None
    if engine == 'leroy':
        assert read(case / 'leroy-run.json')['status'] == 'succeeded', 'Original Rust job did not succeed'
    else:
        job = read(case / 'jenkins-build.json')
        assert not job['building'] and job['result'] == 'SUCCESS', 'Original Rust job did not succeed'
    evidence = original_group_evidence(case, engine, vm.COMMIT, 'quality', 'server-test')
    assert evidence['requested_passed'] and evidence['cleanup_complete']
    assert evidence['rust']['failed'] == 0 and evidence['same_full_rust_test_inventory_as_original']
    summary = read(case / (engine + '-memory-summary.json'))
    assert summary['aligned_guest_host_samples'] > 0
    assert summary['minimum_host_available_kib'] >= 128 * 1024, 'Observed NAS RAM reserve undershoot'
    assert summary['minimum_host_swap_free_kib'] >= 2304 * 1024, 'Observed NAS swap reserve undershoot'
    return evidence


def qualify_rust(folder, remote, engine):
    """A fresh original Rust job gates the full run inside the same deadline."""
    case = FOLLOWUP / qualification_round(engine)
    assert not case.exists(), 'Retain the previous Rust qualification; never retry it implicitly'
    args = [sys.executable, str(ROOT / 'scripts/diagnose_nas_release_group.py'), '--folder',
            case.relative_to(ROOT).as_posix(), '--engine', engine, '--group', 'server-test',
            '--resource-profile', PROFILE, '--postgres-init', '--memory-trace']
    process = None
    registered = None
    with (folder / 'rust-stdout.log').open('w', encoding='utf-8') as out, (folder / 'rust-stderr.log').open('w', encoding='utf-8') as err:
        try:
            process = subprocess.Popen(args, cwd=ROOT, stdout=out, stderr=err)
            write(folder / 'rust-process-started.json', {'pid': process.pid, 'original_ci_restarted': False})
            last_guard = 0
            while process.poll() is None:
                marker = case / 'leroy-start.json'
                if engine == 'leroy' and registered is None and marker.exists():
                    registered = read(marker)['id']
                    action(remote, 'register', registered)
                if time.monotonic() - last_guard >= 60:
                    state = action(remote, 'status')
                    write(folder / 'latest-window-state.json', state)
                    last_guard = time.monotonic()
                    assert state['phase'] == 'paused', 'Window ended during Rust qualification'
                time.sleep(10)
            write(folder / 'rust-process-result.json', {'exit_code': process.returncode, 'original_ci_restarted': False})
            assert process.returncode == 0, 'Rust collection failed; full release will not start'
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=20)
    evidence = require_rust_evidence(case, engine)
    state = action(remote, 'status')
    # Keep two hours for the full run and its independent 15-minute recovery margin.
    assert state['phase'] == 'paused' and state['deadline'] - time.time() >= 8100
    write(folder / 'rust-qualification.json', {'engine': engine, 'original_evidence': evidence,
          'at': datetime.now(timezone.utc).isoformat(), 'full_release_acceptance_complete': False})
    print(json.dumps({'engine': engine, 'original_rust_qualified': True}), flush=True)


def run_window(engine):
    require_window_approval()
    folder = FOLLOWUP / window_name(engine)
    folder.mkdir(parents=True, exist_ok=True)
    assert not (folder / 'prepared-window.json').exists(), 'Inspect the retained window; never grant another deadline'
    remote = '/volume1/docker/leroy-nas-parity/' + folder.name
    case = FOLLOWUP / ROUND
    case.mkdir(exist_ok=True)
    prepare(folder, remote, engine)
    stopped = threading.Event()
    threads = []
    process = None
    try:
        state = action(remote, 'pause')
        write(folder / 'paused.json', state)
        print(json.dumps({'engine': engine, 'services_paused': True, 'started_at_epoch': state['started_at'],
                          'deadline_epoch': state['deadline'], 'restore_margin_seconds': state['restore_margin_seconds']}), flush=True)
        if ROUND == RECONCILE_ROUND:
            qualify_rust(folder, remote, engine)
        threads = [threading.Thread(target=observe_control, args=(folder, stopped), daemon=True),
                   threading.Thread(target=observe_owned_jobs, args=(folder, stopped), daemon=True)]
        for thread in threads:
            thread.start()
        args = [sys.executable, str(ROOT / 'scripts/compare_nas_full_release.py'), '--folder',
                case.relative_to(ROOT).as_posix(), '--engine', engine, '--first-engine', 'leroy',
                '--resource-profile', PROFILE]
        if ROUND == RECONCILE_ROUND:
            args.append('--postgres-init')
        registered = set()
        previous = None
        with (folder / 'ci-stdout.log').open('w', encoding='utf-8') as out, (folder / 'ci-stderr.log').open('w', encoding='utf-8') as err:
            process = subprocess.Popen(args, cwd=ROOT, stdout=out, stderr=err)
            write(folder / 'ci-process-started.json', {'pid': process.pid, 'original_ci_restarted': False})
            last_guard = 0
            while process.poll() is None:
                progress = case / (engine + '-progress.json')
                if progress.exists():
                    value = read(progress)
                    current = value.get('runs', value.get('builds', {}))
                    if engine == 'leroy':
                        for row in current.values():
                            if row['id'] not in registered:
                                action(remote, 'register', row['id'])
                                registered.add(row['id'])
                    if current != previous:
                        print(json.dumps({'engine': engine, 'original_ci': current}), flush=True)
                        previous = current
                marker = case / 'leroy-start.json'
                if engine == 'leroy' and marker.exists():
                    identity = read(marker)['id']
                    if identity not in registered:
                        action(remote, 'register', identity)
                        registered.add(identity)
                if time.monotonic() - last_guard >= 60:
                    state = action(remote, 'status')
                    write(folder / 'latest-window-state.json', state)
                    last_guard = time.monotonic()
                    if state['phase'] != 'paused':
                        write(folder / 'window-interrupted.json', {'phase': state['phase'],
                              'original_ci_restarted': False, 'full_release_acceptance_complete': False})
                        process.terminate()
                        process.wait(timeout=20)
                        break
                time.sleep(10)
        write(folder / 'ci-process-result.json', {'exit_code': process.returncode, 'original_ci_restarted': False})
    except Exception as error:
        write(folder / 'operation-error.json', {'type': type(error).__name__, 'original_ci_restarted': False})
        raise
    finally:
        # NAS watchdog acts independently if this SSH request or Windows fails.
        if process is not None and process.poll() is not None:
            try:
                vm.stop()
            except Exception as error:
                write(folder / 'clean-vm-stop-error.json', {'type': type(error).__name__})
        state = action(remote, 'restore')
        write(folder / 'restored-window.json', state)
        stopped.set()
        for thread in threads:
            thread.join(timeout=30)
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=20)
        recovery = verify_recovery(folder, remote)
        after = infrastructure()
        write(folder / 'infrastructure-after.json', after)
        before = read(folder / 'infrastructure-before.json')
        production = production_jobs()
        write(folder / 'production-after.json', production)
        same = all(before[key] == after[key] for key in
                   ('services', 'postgres_durability', 'configuration_sha256', 'comparison_driver_sha256'))
        stable = before['states']['controller'] == after['states']['controller']
        no_oom = all(after['controller_memory']['memory.events'][key] ==
                     before['controller_memory']['memory.events'][key] for key in ('oom', 'oom_kill'))
        result = {'at': datetime.now(timezone.utc).isoformat(), 'engine': engine, 'commit': vm.COMMIT,
                  'all_seven_original_services_restored_healthy': True,
                  'restored_before_deadline': state['finished_at'] < state['deadline'],
                  'healthy_before_deadline': recovery['at_epoch'] < state['deadline'],
                  'elapsed_window_minutes': (state['finished_at'] - state['started_at']) / 60,
                  'controller_unchanged_without_restart': stable, 'controller_no_new_cgroup_oom': no_oom,
                  'same_infrastructure_within_window': same,
                  'native_jenkins_quiet': not production['active_builds'] and
                      production['jobs'] == read(folder / 'production-before.json')['jobs'],
                  'original_ci_restarted': False, 'production_ready': False}
        write(folder / 'window-result.json', result)
        print(json.dumps(result), flush=True)
        assert result['restored_before_deadline'] and result['healthy_before_deadline']
        assert same, 'Infrastructure changed during original comparison; retain observed evidence'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=('leroy', 'jenkins'), required=True)
    parser.add_argument('--round', choices=(LEGACY_ROUND, RECONCILE_ROUND), default=LEGACY_ROUND)
    args = parser.parse_args()
    configure_comparison(args.round)
    run_window(args.engine)


if __name__ == '__main__':
    main()
