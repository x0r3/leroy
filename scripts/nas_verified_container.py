"""Pin a NAS container once, then verify its live process without Docker RPCs.

These checks never refresh a changed identity. A restart or replaced mount ends
the observation instead of silently selecting another process or data volume.
"""

import json

HELPERS = r'''
import hashlib,json,pathlib,re
def process_identity(pid):
 p=pathlib.Path('/proc',str(pid));fields=(p/'stat').read_text().rpartition(') ')[2].split()
 assert fields[0]!='Z','Pinned container process ended'
 return {'start_ticks':fields[19],'cgroup':(p/'cgroup').read_text(),
         'namespaces':{n:str((p/'ns'/n).readlink()) for n in ('mnt','net','pid')},
         'command_sha256':hashlib.sha256((p/'cmdline').read_bytes()).hexdigest()}
def directory_identity(path):
 p=pathlib.Path(path);s=p.stat();assert p.is_dir()
 return {'device':s.st_dev,'inode':s.st_ino}
def verify_pin(pin):
 assert re.fullmatch('[a-f0-9]{64}',pin['container_id']) and type(pin['pid']) is int and pin['pid']>0
 assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()==pin['boot_id']
 actual=process_identity(pin['pid']);assert actual==pin['process'],'Pinned container process changed'
 parts=[p for line in actual['cgroup'].splitlines() for p in line.split(':',2)[-1].split('/')]
 assert pin['container_id'] in parts or 'docker-'+pin['container_id']+'.scope' in parts
 for destination,mount in pin['mounts'].items():
  p=pathlib.Path(mount['source']);assert p.resolve(strict=True)==p
  assert directory_identity(p)==mount['directory'],'Pinned mount source replaced'
  target=pathlib.Path('/proc',str(pin['pid']),'root')/destination.lstrip('/')
  assert directory_identity(target)==mount['directory'],'Pinned process mount changed'
 return pin
'''


def discover_program(name, *, labels=None, mounts=(), retained_labels=()):
    """One bounded discovery; subsequent programs must use verify_program."""
    assert name in {'jenkins', 'leroy-nas-release-target-vm'}
    constants = {'NAME': name, 'EXPECTED_LABELS': labels or {}, 'MOUNTS': list(mounts),
                 'RETAIN_LABELS': list(retained_labels)}
    return ''.join(key + '=' + repr(value) + '\n' for key, value in constants.items()) + HELPERS + r'''
import subprocess
info=json.loads(subprocess.check_output(['docker','inspect',NAME],text=True,timeout=20))[0]
assert info['Name']=='/'+NAME and info['State']['Running'] and not info['State']['Paused']
assert all(info['Config']['Labels'].get(k)==v for k,v in EXPECTED_LABELS.items())
mounts={}
for destination in MOUNTS:
 row,=[m for m in info['Mounts'] if m['Destination']==destination]
 source=str(pathlib.Path(row['Source']).resolve(strict=True))
 mounts[destination]={'source':source,'directory':directory_identity(source)}
pin={'container_id':info['Id'],'pid':info['State']['Pid'],
     'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
     'process':process_identity(info['State']['Pid']),'mounts':mounts,
     'labels':{k:info['Config']['Labels'][k] for k in (*EXPECTED_LABELS,*RETAIN_LABELS)}}
verify_pin(pin)
print(json.dumps(pin))
'''


def verify_program(pin):
    # JSON encoding is transported as Python source, never as shell quoting.
    return HELPERS + '\nPIN=json.loads(' + repr(json.dumps(pin)) + ')\nverify_pin(PIN)\n'
