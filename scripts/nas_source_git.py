"""Read the frozen checkout with Git from the already pinned NAS Jenkins image."""
import os
import subprocess
import sys
from pathlib import Path

import nas_native
from nas_ssh import ROOT


def command(arguments, cwd, identity):
    source = ROOT / '.sources/frozen-master/graphato-0ad540dd5780'
    assert cwd.resolve() == source.resolve() and cwd == source
    assert arguments in (['rev-parse', 'HEAD'], ['status', '--porcelain'])
    image = identity['git_image']
    import re

    assert re.fullmatch('sha256:[a-f0-9]{64}', image)
    return ['docker', 'run', '--rm', '--pull=never', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
            '--user', '0:0', '--memory', '128m', '--memory-swap', '128m', '--cpus', '0.25',
            '--pids-limit', '32', '--env', 'GIT_OPTIONAL_LOCKS=0',
            '--mount', 'type=bind,src=' + str(source) + ',dst=' + str(source) + ',readonly',
            '--workdir', str(source), '--entrypoint', '/usr/bin/git', image,
            '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false', *arguments]


if __name__ == '__main__':
    assert nas_native.enabled()
    identity = nas_native.validate(ROOT)
    raise SystemExit(subprocess.call(command(sys.argv[1:], Path(os.getcwd()), identity)))
