"""Preserve the OOM-aborted owned VM disk, then restart after unrelated tests finish."""

import json
import subprocess

from fetch_native_graphato_runtime import EVIDENCE
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT
from nas_target_host_guard import begin as host_begin
from nas_target_host_guard import finish as host_finish
from nas_target_host_guard import state
from prepare_nas_vm import guest, wait_guest_ready


def main():
    marker = EVIDENCE / 'runtime-import-vm-recovery.json'
    assert not marker.exists(), 'Retain the first recovery observation'
    info = json.loads(subprocess.check_output(['docker', 'inspect', 'leroy-nas-target-vm'], text=True))[0]
    assert not info['State']['Running'] and info['State']['OOMKilled']
    assert next(m['Name'] for m in info['Mounts'] if m['Destination'] == '/vm') == 'leroy-nas-target_disk'
    crash = EVIDENCE / 'runtime-import-global-oom.json'
    if not crash.exists():
        output = subprocess.check_output(['wsl', '-d', 'docker-desktop', '--', 'dmesg'], text=True)
        lines = [line for line in output.splitlines() if any(word in line for word in (
            'oom-kill:', 'Out of memory: Killed process', 'qemu-system', 'rustc', 'Free swap', 'Total swap'))]
        crash.write_text(json.dumps({'container_state': info['State'], 'container_id': info['Id'],
                                    'outer_memory_limit_bytes': info['HostConfig']['Memory'],
                                    'kernel_memory_diagnostic_lines': lines,
                                    'target_host_state_after_failure': state(),
                                    'test_started': False, 'production_modified': False}, indent=2) + '\n')
    host_before = host_begin(EVIDENCE, 'vm-import-recovery', required_available_gib=11)
    idle()
    before = begin(EVIDENCE, 'vm-import-recovery')
    current = json.loads(subprocess.check_output(['docker', 'inspect', 'leroy-nas-target-vm'], text=True))[0]
    assert current['Id'] == info['Id'] and not current['State']['Running']
    snapshot = 'after-oom-native-runtime-import-0ad540dd5780'
    subprocess.run(['docker', 'compose', '-f', 'infra/nas/compose.target-vm.yaml', 'run', '--rm', '--no-deps',
                    '--entrypoint', 'qemu-img', 'vm', 'snapshot', '-c', snapshot, '/vm/system.qcow2'],
                   cwd=ROOT, capture_output=True, check=True, timeout=240)
    subprocess.run(['docker', 'start', 'leroy-nas-target-vm'], check=True, capture_output=True, timeout=60)
    wait_guest_ready()
    observed = json.loads(guest('sudo python3 -B -', '''
import hashlib,json,os,pathlib,subprocess
p=pathlib.Path('/opt/graphato/current/manifest.json');v=json.loads(p.read_text())
assert v['commit']=='0ad540dd578033d45e4d0c25d89fbe57b32102a4'
assert v['runtimeImageId']=='sha256:6251c60f499e41e706613f931bf281ce52312b957d5a6a123cf4e27dd3242585'
assert os.cpu_count()==4
print(json.dumps({'commit':v['commit'],'runtime_image_id':v['runtimeImageId'],'active_manifest_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()}))
''', timeout=30))
    value = {'preserved_crash_snapshot': snapshot, 'vm_restarted': True,
             'guest_cpu_and_memory_configuration_changed': False,
             'observed': observed, 'test_files_modified': False, 'application_files_modified': False,
             'production_modified': False, 'external_workloads_modified': False,
             'target_host_qualification': host_finish(EVIDENCE, 'vm-import-recovery', host_before),
             'production_qualification': finish(EVIDENCE, 'vm-import-recovery', before)}
    marker.write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({'vm_restarted': True, 'crash_snapshot_preserved': snapshot,
                      'original_active_runtime_image_retained': True}), flush=True)


if __name__ == '__main__':
    main()
