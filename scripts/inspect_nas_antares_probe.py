"""Save bounded read-only resource and reader evidence for an owned browser probe."""

import argparse
import json
import re
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--attempt", required=True)
    args = parser.parse_args()
    assert re.fullmatch(r"[a-f0-9]{40}", args.candidate)
    assert re.fullmatch(r"[a-z0-9-]{1,24}", args.attempt)
    name = "antares-browser-probe-" + args.candidate[:12] + "-" + args.attempt
    program = r"""
import json,pathlib,subprocess
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
outer=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-docker-1'],text=True))[0]
assert outer['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
root=pathlib.Path('/sys/fs/cgroup/system.slice/docker-'+outer['Id']+'.scope')
fields=['cpu.stat','cpu.pressure','memory.current','memory.peak','memory.events','memory.swap.current','memory.pressure','io.pressure']
data={'cgroup':{k:(root/k).read_text().strip() for k in fields if (root/k).exists()}}
prefix=['docker','exec','leroy-nas-parity-docker-1','docker']
probe=json.loads(subprocess.check_output([*prefix,'inspect',NAME],text=True))[0]
assert probe['Config']['Labels']['io.leroy.nas-parity']=='true'
data['reader_counts']=subprocess.check_output([*prefix,'exec',NAME+'-db','psql','-U','antares','-d','antares_test','-Atc',
 'select count(*), max(extract(epoch from (now()-started_at))) from game_state_readers;'],text=True).strip()
data['console_tail']=subprocess.check_output([*prefix,'logs','--tail','15',NAME],text=True,stderr=subprocess.STDOUT)
print(json.dumps(data))
"""
    result = run_script(
        "python3 - <<'PY'\nNAME=" + repr(name) + "\n" + program + "\nPY\n",
        ROOT / ".local/nas-ssh.json",
        sudo=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr[-1500:]
    data = {"at": datetime.now(timezone.utc).isoformat(), **json.loads(result.stdout)}
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / args.candidate
    with (folder / ("focused-browsers-" + args.attempt + "-resources.jsonl")).open(
        "a", encoding="utf-8"
    ) as output:
        output.write(json.dumps(data) + "\n")
    print(json.dumps(data), flush=True)


if __name__ == "__main__":
    main()
