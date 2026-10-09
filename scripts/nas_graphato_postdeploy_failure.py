"""Verify the observed original postdeploy permission rejection without repairing it."""

import argparse
import json

from nas_ssh import ROOT
from prepare_nas_vm import guest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", choices=["jenkins", "leroy"])
    engine = parser.parse_args().engine
    program = r"""
import json,pathlib,runpy,stat,subprocess
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
root=pathlib.Path('/var/lib/graphato-host/postdeploy')
info=root.lstat()
assert not root.is_symlink() and stat.S_ISDIR(info.st_mode)
assert stat.S_IMODE(info.st_mode)==0o755 and info.st_uid==0
assert not list(root.iterdir()),'Existing receipts require a separate diagnosis'
receiver=runpy.run_path('/usr/local/sbin/graphato-ci-receive',run_name='diagnostic')
module=receiver['postdeploy_module']()
assert module.STATE==root
try:
 module.run_marker('0'*32)
except ValueError as exc:
 error=str(exc)
else:raise AssertionError('Observed directory was unexpectedly accepted')
assert error=='Run markers require root-private directories'
assert not list(root.iterdir()),'Diagnostic must not create run markers'
ids=subprocess.check_output(['docker','ps','-q','--filter','label=com.docker.compose.project=graphato-prod','--filter','label=com.docker.compose.service=maintenance'],text=True).split()
assert len(ids)==1
pid=subprocess.check_output(['docker','inspect','--format','{{.State.Pid}}',ids[0]],text=True).strip()
mask=next(line.split()[1] for line in pathlib.Path('/proc',pid,'status').read_text().splitlines() if line.startswith('Umask:'))
print(json.dumps({'directory':str(root),'mode':oct(stat.S_IMODE(info.st_mode)),'uid':info.st_uid,'error':error,'maintenance_umask':mask,'checks_started':False,'application_patches_applied':False}))
"""
    state = json.loads(guest("sudo python3 -", program))
    path = ROOT / f"test-results/nas-parity/aligned/graphato-ci/{engine}-postdeploy-startup-failure.json"
    path.write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps(state))


if __name__ == "__main__":
    main()
