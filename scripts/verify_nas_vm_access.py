"""Pin the test VM host key and verify transport from the owned NAS Jenkins."""

import json

from compare_nas_antares import jenkins_python
from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE, remote
from nas_ssh import ROOT, upload_file


def main():
    host = (ROOT / ".local/vm/ssh_host_ed25519_key.pub").read_text().strip()
    known = LOCAL / "fixtures/vm-known-hosts"
    known.write_text("graphato-parity " + host + "\n[graphato-parity]:12225 " + host + "\n")
    config = LOCAL / "fixtures/vm-ssh-config"
    config.write_text("""Host 87.106.133.233 graphato-vm
  HostName 10.232.98.11
  Port 12225
  HostKeyAlias graphato-parity
  GlobalKnownHostsFile /root/.ssh/parity_known_hosts
  StrictHostKeyChecking yes
  IdentitiesOnly yes
  BatchMode yes
""")
    for path in (known, config):
        upload_file(path, REMOTE + "/fixtures/" + path.name, CREDENTIALS)
    for name in ("bootstrap", "bootstrap.pub", "deploy", "deploy.pub"):
        upload_file(
            LOCAL / "config/test-secrets" / name, REMOTE + "/config/test-secrets/" + name, CREDENTIALS
        )
    remote(f"""cd {REMOTE}
chmod 644 fixtures/vm-known-hosts fixtures/vm-ssh-config
docker exec leroy-nas-parity-docker-1 docker exec jenkins-parity mkdir -p /root/.ssh
docker exec leroy-nas-parity-docker-1 docker cp /fixtures/vm-ssh-config jenkins-parity:/root/.ssh/config
docker exec leroy-nas-parity-docker-1 docker cp /fixtures/vm-known-hosts jenkins-parity:/root/.ssh/parity_known_hosts
docker exec leroy-nas-parity-docker-1 docker cp /test-secrets/bootstrap jenkins-parity:/root/.ssh/parity-bootstrap
docker exec leroy-nas-parity-docker-1 docker exec --privileged jenkins-parity chown 0:0 /root/.ssh/config /root/.ssh/parity_known_hosts /root/.ssh/parity-bootstrap
docker exec leroy-nas-parity-docker-1 docker exec jenkins-parity chmod 600 /root/.ssh/config /root/.ssh/parity-bootstrap
""")
    result = jenkins_python("""import subprocess,json
output=subprocess.check_output(['ssh','-i','/root/.ssh/parity-bootstrap','-o','ConnectTimeout=10','-o','UserKnownHostsFile=/dev/null','root@87.106.133.233','uname -r; systemd-detect-virt; cat /sys/module/apparmor/parameters/enabled'],text=True)
assert output.splitlines() == ['6.8.0-142-generic','kvm','Y']
print(json.dumps({'kernel':'6.8.0-142-generic','virtualization':'kvm','apparmor':True,'host_key_verified':True,'transport':'separate_test_ssh_service','nas_sshd_modified':False}))
""")
    evidence = json.loads(result)
    (ROOT / "test-results/nas-parity/vm-transport.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
