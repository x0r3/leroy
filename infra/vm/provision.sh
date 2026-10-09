#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
test "$(cat /sys/module/apparmor/parameters/enabled)" = Y
systemctl enable --now apparmor
install -m 0755 -d /etc/apt/keyrings /var/lib/leroy-vm
curl --fail --silent --show-error --location https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat >/etc/apt/sources.list.d/docker.sources <<'EOF'
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras
install -m 0755 -d /etc/docker
cat >/etc/docker/daemon.json <<'EOF'
{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}
EOF
systemctl enable docker
systemctl restart docker
docker run --rm --security-opt apparmor=docker-default hello-world
touch /var/lib/leroy-vm/ready
