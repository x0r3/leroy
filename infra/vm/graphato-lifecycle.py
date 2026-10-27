"""Order application shutdown before Docker stops the disposable VM's database."""

import json
import subprocess
import sys
from pathlib import Path


def command():
    assert Path("/var/lib/leroy-vm/ready").is_file()
    assert subprocess.check_output(["systemd-detect-virt"], text=True).strip() == "kvm"
    current = Path("/opt/graphato/current")
    if not current.exists():
        return None
    directory = current.resolve(strict=True)
    assert directory.is_relative_to("/opt/graphato/releases")
    files = ["compose.prod.yaml", "deployments/linux/compose.host.yaml"]
    if (directory / "compose.agent-tests.yaml").is_file():
        files += ["compose.agent-tests.yaml", "deployments/linux/compose.agent-tests.prod.yaml"]
    args = [
        "docker",
        "compose",
        "--project-name",
        "graphato-prod",
        "--env-file",
        str(directory / "release.env"),
    ]
    for name in files:
        args += ["-f", str(directory / name)]
    override = Path('/var/lib/leroy-vm/postgres-init.override.json')
    if override.exists():
        assert not override.is_symlink()
        assert override.stat().st_uid == 0 and override.stat().st_mode & 0o022 == 0
        assert json.loads(override.read_text()) == {'services': {'postgres': {'init': True}}}
        args += ['-f', str(override)]
    return args


def main():
    (action,) = sys.argv[1:]
    assert action in ("start", "stop")
    args = command()
    if args is not None:
        operation = ["up", "-d", "--wait", "--wait-timeout", "180"] if action == "start" else ["stop"]
        subprocess.run([*args, *operation], check=True)


if __name__ == "__main__":
    main()
