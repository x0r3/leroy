"""NAS-local orchestration of the unchanged guest memory probe.

Only this small temporary operator process receives soft protection in the
existing owned slice. Production admission is read locally with the canonical
pinned program, and guest SSH reuses one connection. Host SSH is not on the
allocation path. This file is standalone and uses only the Python standard library.
"""
import contextlib
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

TARGET_MIB = 5888
ALLOCATION_MIB = (512,) * 11 + (256,)
PROBE_EXIT_PROGRAM = r'''
import json,re,subprocess,time
assert re.fullmatch('[a-f0-9]{64}',CID) and 0<=time.time()-SINCE<=1300
raw=subprocess.check_output(['docker','events','--since',str(SINCE),'--until',str(int(time.time())),
 '--filter','type=container','--filter','container='+CID,'--format','{{json .}}'],timeout=10)
assert len(raw)<1024**2
events=[]
for line in raw.splitlines():
 row=json.loads(line);assert row['Type']=='container' and row['Actor']['ID']==CID
 action=row.get('Action')
 if action in ('die','oom','kill','stop','destroy'):
  attrs=row['Actor'].get('Attributes',{})
  event={'action':action,'time_nano':row.get('timeNano')}
  for key in ('exitCode','signal'):
   if key in attrs:
    assert re.fullmatch('[0-9]{1,4}',attrs[key]);event[key]=int(attrs[key])
  events.append(event)
 assert len(events)<=100
print(json.dumps({'container_id':CID,'events':events,'read_only':True,'query_or_source_changed':False,
 'absence_of_events_proves_no_failure':False,'raw_attributes_retained':False}))
'''


class GuestOperationFailed(RuntimeError):
    """Retain failure facts without commands, request bodies, or arbitrary logs."""

    def __init__(self, evidence):
        super().__init__('Pinned guest operation failed; inspect retained failure metadata')
        self.evidence = evidence


def guest_failure_metadata(operation, returncode, stdout, stderr, elapsed, *, timed_out=False):
    assert operation in {'start_probe', 'allocate', 'status', 'stop', 'verify_probe_stopped', 'probe_exit_diagnostic'}
    assert returncode is None or type(returncode) is int
    assert type(timed_out) is bool and elapsed >= 0
    output = stdout or b''
    diagnostic = stderr or b''
    if isinstance(output, str):
        output = output.encode()
    if isinstance(diagnostic, str):
        diagnostic = diagnostic.encode()
    text = diagnostic.decode(errors='replace')
    exceptions = [name for name in ('JSONDecodeError', 'TimeoutError', 'ConnectionRefusedError',
                  'ConnectionResetError', 'BrokenPipeError', 'FileNotFoundError', 'AssertionError')
                  if re.search(r'(?m)^(?:[A-Za-z_][A-Za-z0-9_]*\.)*' + name + r':', text)]
    transport = [name for name in ('Connection timed out during banner exchange', 'Connection refused',
                 'Connection reset', 'Broken pipe', 'not responding') if name in text]
    return {'operation': operation, 'returncode': returncode, 'timed_out': timed_out,
            'elapsed_seconds': round(elapsed, 3), 'stdout_bytes': len(output), 'stderr_bytes': len(diagnostic),
            'stdout_sha256': hashlib.sha256(output).hexdigest(), 'stderr_sha256': hashlib.sha256(diagnostic).hexdigest(),
            'exception_types': exceptions, 'transport_diagnostics': transport,
            'outcome_unknown': True, 'action_repeated': False, 'raw_output_retained': False}


class ProbeKeepalive:
    """Read status on an existing pinned connection while admission is pending."""

    def __init__(self, status, emit, *, interval=25, join_timeout=405):
        self.status, self.emit = status, emit
        self.interval, self.join_timeout = interval, join_timeout
        self.stopping = threading.Event()
        self.error, self.count, self.pending = None, 0, []
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        try:
            while not self.stopping.wait(self.interval):
                value = self.status()
                assert value['kind'] == 'held'
                amount = value['allocated_mib']
                assert type(amount) is int and 0 <= amount <= TARGET_MIB and amount % 256 == 0
                self.count += 1
                assert len(self.pending) < 64
                self.pending.append(('probe_keepalive', {'at_epoch': time.time(), 'allocated_mib': amount,
                                                         'counts_as_hold_or_marker_check': False}))
        except Exception as error:
            self.error = error
            self.stopping.set()
            self.pending.append(('probe_keepalive_failed', {'at_epoch': time.time(), 'error_type': type(error).__name__,
                                                             'outcome_unknown': True, 'allocation_repeated': False}))

    def start(self):
        self.thread.start()

    def check(self):
        if self.error is not None:
            raise RuntimeError('Probe status became unknown; no further allocation') from self.error

    def stop(self):
        self.stopping.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=self.join_timeout)
            assert not self.thread.is_alive(), 'Probe status read remains pending; no success receipt'
        # Keep the status loop independent of slow NAS journal writes as well.
        pending, self.pending = self.pending, []
        for kind, value in pending:
            self.emit(kind, value)


def existing_mux_command(ssh, path):
    info = path.lstat()
    assert path.resolve(strict=True) == path and stat.S_ISSOCK(info.st_mode)
    assert info.st_uid == 0 and info.st_nlink == 1 and info.st_mode & 0o077 == 0
    assert ssh[:2] == ['nsenter', '-t'] and ssh[3:5] == ['-n', 'ssh']
    # A missing master must fail locally. No new network namespace, connection,
    # identity discovery or allocation is permitted on this read-only path.
    command = [part if part != 'ControlMaster=auto' else 'ControlMaster=no' for part in ssh[4:]]
    assert 'ControlPath=' + str(path) in command
    return command[:-2] + ['-o', 'ProxyCommand=false'] + command[-2:]


def admission(before, current, memory, amount):
    assert not current['active_builds'] and current['jobs'] == before['jobs'], 'Production changed; no allocation'
    assert memory['MemAvailable'] >= (128 + 128) * 1024, 'NAS available-memory reserve'
    assert memory['SwapFree'] >= (2304 + amount + 256) * 1024, 'NAS swap reserve'


def require_limits(started, image, source_sha256):
    assert started['image'] == image
    assert started['memory_bytes'] == started['memory_and_swap_bytes'] == 6 * 1024**3
    assert started['nano_cpus'] == 2 * 10**9 and started['cgroup_swap_max'] == 0
    assert started['program_sha256'] == source_sha256
    assert started['hard_timeout_seconds'] == 1200 and started['idle_timeout_seconds'] == 120


def sequence(before, production, memory, control, emit, *, sleep=time.sleep):
    """No allocation is retried, including when its response is unknown."""
    phases, stopped = [], False
    try:
        total = 0
        for amount in ALLOCATION_MIB:
            current, reserve = production(), memory()
            admission(before, current, reserve, amount)
            value = control({'action': 'allocate', 'mib': amount})
            total += amount
            assert value['kind'] == 'allocated' and value['allocated_mib'] == total
            phases.append({**value, 'host_before_kib': reserve})
            emit('phase', phases[-1])
            sleep(5)
        assert total == TARGET_MIB
        for _ in range(3):
            sleep(20)
            current = production()
            assert not current['active_builds'] and current['jobs'] == before['jobs']
            value = control({'action': 'status'})
            assert value['kind'] == 'held' and value['allocated_mib'] == TARGET_MIB
            phases.append(value)
            emit('phase', value)
        value = control({'action': 'stop'})
        stopped = True
        assert value['kind'] == 'stopped' and value['all_page_markers_intact'] is True
        phases.append(value)
        emit('phase', value)
        return phases
    finally:
        if not stopped:
            try:
                control({'action': 'stop'})
            except Exception as error:
                emit('cleanup_error', {'error_type': type(error).__name__})


def private_file(path):
    value = path.lstat()
    assert path.resolve(strict=True) == path and not path.is_symlink()
    assert stat.S_ISREG(value.st_mode) and value.st_uid == 0 and value.st_nlink == 1
    assert value.st_mode & 0o077 == 0
    return path.read_bytes()


def working_set():
    relative = next(line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::'))
    group = Path('/sys/fs/cgroup') / relative.lstrip('/')
    assert group.resolve(strict=True) == group and group.parent == Path('/sys/fs/cgroup/leroyparity.slice')
    values = {name: (group / name).read_text().strip() for name in
              ('memory.low', 'memory.min', 'memory.max', 'memory.swap.max', 'cpu.max', 'pids.max')}
    assert values['memory.low'] == str(32 * 1024**2) and values['memory.min'] == '0'
    assert values['memory.max'] == str(128 * 1024**2) and values['memory.swap.max'] == '0'
    quota, period = map(int, values['cpu.max'].split())
    assert quota * 2 == period and values['pids.max'] == '64'
    assert (group.parent / 'memory.low').read_text().strip() == str(448 * 1024**2)
    return {'cgroup_path': str(group), **values, 'global_settings_changed': False}


def main(config_path, expected_config_sha256):
    work = Path(__file__).resolve().parent
    owner = Path('/volume1/docker/leroy-nas-parity')
    assert os.geteuid() == 0 and work.parent == owner and (owner / '.leroy-owned').is_file()
    assert work.resolve(strict=True) == work and work.stat().st_uid == 0 and work.stat().st_mode & 0o077 == 0
    assert config_path == work / 'config.json'
    raw = private_file(config_path)
    assert hashlib.sha256(raw).hexdigest() == expected_config_sha256
    config = json.loads(raw)
    assert config['engine'] in {'leroy', 'jenkins'} and re.fullmatch('[a-z0-9-]{1,64}', config['round'])
    tag = hashlib.sha256((config['round'] + ':' + config['engine']).encode()).hexdigest()[:12]
    assert work.name == 'capacity-agent-' + tag
    assert hashlib.sha256(private_file(work / 'agent.py')).hexdigest() == config['source_sha256']
    verifier = {}
    exec(compile(config['pin_verifier_source'], '<pinned-verifier>', 'exec'), verifier)
    resources = working_set()
    window = owner / config['window']
    assert window.resolve(strict=True) == window and window.stat().st_uid == 0 and window.stat().st_mode & 0o077 == 0
    assert re.fullmatch('resource-window-day-[a-z0-9-]+', config['window'])
    assert hashlib.sha256(private_file(window / 'guard.py')).hexdigest() == config['guard_sha256']
    pin = config['vm_pin']
    assert pin['labels'] == {'io.leroy.nas-release-target': config['commit'],
                             'io.leroy.comparison': config['round'], 'io.leroy.engine': config['engine']}

    def verify():
        verifier['verify_pin'](pin)
        assert hashlib.sha256(private_file(window / 'guard.py')).hexdigest() == config['guard_sha256']
        state = json.loads(private_file(window / 'state.json'))
        assert state['phase'] == 'paused' and state['comparison_rounds'] == [config['round']]
        assert time.time() < state['deadline'] - 900
        assert state['owned_vm_process']['pid'] == pin['pid']

    def save(name, value):
        path = work / name
        data = (json.dumps(value, separators=(',', ':')) + '\n').encode()
        temporary = path.with_suffix(path.suffix + '.partial')
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)

    def emit(kind, value):
        with (work / 'events.jsonl').open('a') as stream:
            stream.write(json.dumps({'kind': kind, 'value': value}, separators=(',', ':')) + '\n')
            stream.flush()
        (work / 'events.jsonl').chmod(0o600)

    ssh = ['nsenter', '-t', str(pin['pid']), '-n', 'ssh', '-T', '-i', config['remote'] + '/admin-key', '-p', '12225',
           '-o', 'UserKnownHostsFile=' + config['remote'] + '/known_hosts', '-o', 'HostKeyAlias=graphato-parity',
           '-o', 'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
           '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3', '-o', 'ControlMaster=auto',
           '-o', 'ControlPersist=600', '-o', 'ControlPath=' + str(work / 'guest.sock'),
           'leroy-admin@127.0.0.1', 'sudo python3 -B -']
    assert config['remote'] == '/volume1/docker/leroy-nas-parity/release-vm/0ad540dd5780'
    assert len(str(work / 'guest.sock').encode()) < 100

    def guest(program, timeout, *, operation):
        verify()
        begin = time.monotonic()
        try:
            result = subprocess.run(ssh, input=program.encode(), capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            evidence = guest_failure_metadata(operation, None, error.stdout, error.stderr,
                                              time.monotonic() - begin, timed_out=True)
            emit('guest_failure', evidence)
            raise GuestOperationFailed(evidence) from error
        verify()
        if result.returncode:
            evidence = guest_failure_metadata(operation, result.returncode, result.stdout, result.stderr,
                                              time.monotonic() - begin)
            emit('guest_failure', evidence)
            raise GuestOperationFailed(evidence)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            evidence = guest_failure_metadata(operation, result.returncode, result.stdout, result.stderr,
                                              time.monotonic() - begin)
            evidence['response_json_invalid'] = True
            emit('guest_failure', evidence)
            raise GuestOperationFailed(evidence) from error

    def production():
        verify()
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            exec(compile(config['production_program'], '<canonical-production-read>', 'exec'), {})
        return json.loads(capture.getvalue())

    def memory():
        return {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()
                if line.startswith(('MemAvailable:', 'SwapFree:'))}

    keeper = None

    def control(action):
        if keeper is not None:
            if action['action'] == 'stop':
                keeper.stop()
            else:
                keeper.check()
        return guest('ACTION=' + repr(action) + '\n' + config['control_program'], 405, operation=action['action'])

    def keepalive_status():
        command = existing_mux_command(ssh, work / 'guest.sock')
        program = "ACTION={'action':'status'}\n" + config['control_program']
        begin = time.monotonic()
        try:
            result = subprocess.run(command, input=program.encode(), capture_output=True, timeout=405)
        except subprocess.TimeoutExpired as error:
            evidence = guest_failure_metadata('status', None, error.stdout, error.stderr,
                                              time.monotonic() - begin, timed_out=True)
            emit('guest_failure', evidence)
            raise GuestOperationFailed(evidence) from error
        if result.returncode:
            evidence = guest_failure_metadata('status', result.returncode, result.stdout, result.stderr,
                                              time.monotonic() - begin)
            emit('guest_failure', evidence)
            raise GuestOperationFailed(evidence)
        return json.loads(result.stdout)

    verify()
    save('identity.json', {'pid': os.getpid(), 'config_sha256': expected_config_sha256,
                           'source_sha256': config['source_sha256'], 'resources': resources,
                           'start_ticks': Path('/proc/self/stat').read_text().rpartition(') ')[2].split()[19],
                           'command_sha256': hashlib.sha256(Path('/proc/self/cmdline').read_bytes()).hexdigest(),
                           'at_epoch': time.time(), 'round': config['round'], 'engine': config['engine']})
    started, probe_started_at = None, time.time()
    try:
        before = production()
        assert not before['active_builds'] and before['jobs'] == config['expected_production_jobs']
        program = ('IMAGE=' + repr(config['image']) + '\nNAME=' + repr(config['probe_name']) +
                   '\nAGENT=' + repr(config['guest_agent']) + '\n' + config['start_program'])
        started = guest(program, 45, operation='start_probe')
        try:
            require_limits(started, config['image'], hashlib.sha256(config['guest_agent'].encode()).hexdigest())
        except Exception:
            try:
                control({'action': 'stop'})
            except Exception as error:
                emit('cleanup_error', {'error_type': type(error).__name__})
            raise
        save('started.json', started)
        keeper = ProbeKeepalive(keepalive_status, emit)
        keeper.start()
        try:
            phases = sequence(before, production, memory, control, emit)
        finally:
            keeper.stop()
        keeper.check()
        check = ('import json,subprocess\nprint(json.dumps(subprocess.check_output(' +
                 repr(['docker', 'ps', '-q', '--filter', 'name=^/' + config['probe_name'] + '$']) + ').decode().strip()))')
        for _ in range(30):
            if not guest(check, 15, operation='verify_probe_stopped'):
                break
            time.sleep(1)
        else:
            raise RuntimeError('Synthetic container remains active')
        proof = {'qualified_synthetic_capacity': True, 'allocated_mib': TARGET_MIB, 'hold_seconds': 60,
                 'all_page_markers_intact': True, 'original_fixture_limits_emulated': True, 'limits': started,
                 'original_ci_dispatched': False, 'application_source_or_tests_changed': False,
                 'host_swap_changed': False, 'full_release_acceptance_complete': False, 'phases': phases,
                 'nas_local_admission': True, 'driver_resources': resources,
                 'config_sha256': expected_config_sha256, 'driver_source_sha256': config['source_sha256']}
        proof['active_probe_keepalive'] = {'status_reads': keeper.count, 'stopped': not keeper.thread.is_alive(),
                                           'existing_mux_only': True, 'counts_as_hold_or_marker_check': False,
                                           'idle_and_hard_timeout_limits_changed': False}
        save('result.json', proof)
    except Exception as error:
        failure = {'at_epoch': time.time(), 'error_type': type(error).__name__,
                   'original_ci_dispatched': False, 'config_sha256': expected_config_sha256}
        if isinstance(error, GuestOperationFailed):
            failure['guest_failure'] = error.evidence
        if started is not None:
            try:
                program = 'CID=' + repr(started['container_id']) + '\nSINCE=' + repr(int(probe_started_at)) + '\n' + PROBE_EXIT_PROGRAM
                emit('probe_exit', guest(program, 20, operation='probe_exit_diagnostic'))
            except Exception as diagnostic_error:
                emit('probe_exit_unknown', {'error_type': type(diagnostic_error).__name__,
                                            'outcome_unknown': True, 'action_repeated': False})
        save('failed.json', failure)
        raise


if __name__ == '__main__':
    assert len(sys.argv) == 3
    main(Path(sys.argv[1]), sys.argv[2])
