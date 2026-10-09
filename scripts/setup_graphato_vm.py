"""Connect only the isolated test runner to the own-kernel Graphato VM."""

import ast
import json
import shlex
import subprocess
import tomllib

from test_support import ROOT
from test_vm import guest


def main():
    # The upstream host policy deliberately rejects a different installed Docker
    # version. Match its reviewed pins on the disposable VM before bootstrap.
    tree = ast.parse(
        (ROOT / ".sources/graphato/deployments/linux/host/bootstrap.py").read_text(encoding="utf-8")
    )
    pins = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "DOCKER_PACKAGES" for target in node.targets)
    )
    installed = json.loads(
        guest(
            "python3 -c \"import subprocess,json; print(json.dumps({p:subprocess.check_output(['dpkg-query','-W','-f=\\${Version}',p],text=True) for p in ['docker-ce','docker-ce-cli','containerd.io','docker-buildx-plugin','docker-compose-plugin']}))\""
        )
    )
    if installed != pins:
        guest("sudo test ! -e /opt/graphato/current")
        packages = [f"{name}={version}" for name, version in pins.items()]
        packages.append("docker-ce-rootless-extras=" + pins["docker-ce"])
        guest(
            "sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --allow-downgrades "
            + shlex.join(packages)
            + " >/var/tmp/leroy-docker-pins.log 2>&1"
        )
        print("VM Docker packages aligned with the original Graphato host policy.")
    info = json.loads(subprocess.check_output(["docker", "inspect", "leroy-linux-vm"]))[0]
    network = info["NetworkSettings"]["Networks"].get("leroy-test_default")
    if network is None:
        subprocess.run(
            ["docker", "network", "connect", "--ip", "10.231.88.11", "leroy-test_default", "leroy-linux-vm"],
            check=True,
        )
    elif network["IPAddress"] != "10.231.88.11":
        raise ValueError("Unexpected VM address on the isolated test network")
    public = (ROOT / ".local/test-secrets/bootstrap.pub").read_text(encoding="utf-8").strip()
    if not public.startswith("ssh-ed25519 ") or "\n" in public:
        raise ValueError("Expected one generated test bootstrap public key")
    guest("sudo install -d -m 700 /root/.ssh")
    guest(
        "sudo sh -c 'cat >> /root/.ssh/authorized_keys; sort -u /root/.ssh/authorized_keys -o /root/.ssh/authorized_keys; chmod 600 /root/.ssh/authorized_keys'",
        data=public + "\n",
    )
    host_key = (ROOT / ".local/vm/ssh_host_ed25519_key.pub").read_text(encoding="utf-8").strip()
    known = ROOT / ".local/test-secrets/known_hosts"
    lines = [
        line
        for line in known.read_text(encoding="utf-8").splitlines()
        if not line.startswith("[graphato-vm]:2222 ")
    ]
    known.write_text("\n".join([*lines, "[graphato-vm]:2222 " + host_key]) + "\n", encoding="utf-8")
    config = ROOT / ".local/runner.test.toml"
    content = config.read_text(encoding="utf-8")
    content = content.replace(
        'host_mappings = {controller = "10.231.88.10"}',
        'host_mappings = {controller = "10.231.88.10", graphato-vm = "10.231.88.11"}',
    )
    content = content.replace('host = "graphato-target"', 'host = "graphato-vm"\nport = 2222')
    parsed = tomllib.loads(content)
    assert parsed["profiles"]["default"]["host_mappings"]["graphato-vm"] == "10.231.88.11"
    assert parsed["profiles"]["default"]["graphato"]["port"] == 2222
    assert parsed["profiles"]["default"]["graphato"]["host"] == "graphato-vm"
    config.write_text(content, encoding="utf-8")
    (ROOT / ".local/vm/acceptance-enabled").touch()
    print("VM target configured with a pinned host key; restart the isolated runner to reload its profile.")


if __name__ == "__main__":
    main()
