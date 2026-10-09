#!/bin/bash
# Run only inside the disposable Leroy VM. No CA or DNS change on Windows.
set -euo pipefail
test -f /var/lib/leroy-vm/ready
test "$(systemd-detect-virt)" = kvm
install -d -m 700 /var/lib/leroy-vm/acme
cd /var/lib/leroy-vm/acme
if ! test -f root.pem; then
    openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj '/CN=Leroy isolated ACME transport' -keyout root.key -out root.pem -addext basicConstraints=critical,CA:TRUE -addext keyUsage=critical,keyCertSign,cRLSign 2>/dev/null
    openssl req -new -newkey rsa:2048 -nodes -subj '/CN=acme-v02.api.letsencrypt.org' -keyout server.key -out server.csr 2>/dev/null
    printf 'subjectAltName=DNS:acme-v02.api.letsencrypt.org\nextendedKeyUsage=serverAuth\nbasicConstraints=CA:FALSE\n' >server.ext
    openssl x509 -req -in server.csr -CA root.pem -CAkey root.key -CAcreateserial -days 30 -extfile server.ext -out server.pem 2>/dev/null
    chmod 600 *.key
fi
# A simulated globally-shaped address is local to this guest. The outer QEMU
# firewall also rejects it, preventing any accidental packet from leaving.
ip link show leroy-public >/dev/null 2>&1 || ip link add leroy-public type dummy
ip address replace 11.254.254.254/32 dev leroy-public
ip link set leroy-public up
python3 - <<'PY'
from pathlib import Path
path=Path('/etc/hosts')
lines=[line for line in path.read_text().splitlines() if ' # leroy-acme-test' not in line]
path.write_text('\n'.join([*lines,'11.254.254.254 graphato.test # leroy-acme-test','172.31.90.2 acme-v02.api.letsencrypt.org # leroy-acme-test'])+'\n')
PY
docker network inspect leroy-acme >/dev/null 2>&1 || docker network create --subnet 172.31.90.0/24 leroy-acme
cat >pebble.json <<'EOF'
{"pebble":{"listenAddress":"0.0.0.0:14000","managementListenAddress":"0.0.0.0:15000","certificate":"/config/server.pem","privateKey":"/config/server.key","httpPort":80,"tlsPort":443,"externalAccountBindingRequired":false}}
EOF
if ! docker inspect leroy-acme-pebble >/dev/null 2>&1; then
    docker run -d --name leroy-acme-pebble --network leroy-acme --ip 172.31.90.2 --add-host graphato.test:11.254.254.254 --restart unless-stopped --memory 128m --cpus 0.5 --env PEBBLE_VA_NOSLEEP=1 --mount type=bind,source=/var/lib/leroy-vm/acme,target=/config,readonly ghcr.io/letsencrypt/pebble:2.9.0 -config /config/pebble.json
fi
docker start leroy-acme-pebble >/dev/null
if ! docker inspect leroy-acme-directory >/dev/null 2>&1; then
    docker run -d --name leroy-acme-directory --network container:leroy-acme-pebble --restart unless-stopped --memory 64m --cpus 0.25 --mount type=bind,source=/var/lib/leroy-vm/acme,target=/config,readonly python:3.14.3-slim-bookworm python /config/acme-directory.py
fi
docker start leroy-acme-directory >/dev/null
install -m 644 root.pem /usr/local/share/ca-certificates/leroy-acme-transport.crt
if test -s /usr/local/share/ca-certificates/leroy-acme-issuer.crt; then
    fingerprint=$(sha256sum /usr/local/share/ca-certificates/leroy-acme-issuer.crt | cut -c1-16)
    cp /usr/local/share/ca-certificates/leroy-acme-issuer.crt "/usr/local/share/ca-certificates/leroy-acme-issuer-${fingerprint}.crt"
fi
for attempt in $(seq 1 30); do
    if curl --fail --silent --show-error --cacert root.pem https://acme-v02.api.letsencrypt.org:15000/roots/0 -o /usr/local/share/ca-certificates/leroy-acme-issuer.crt; then break; fi
    sleep 1
done
test -s /usr/local/share/ca-certificates/leroy-acme-issuer.crt
update-ca-certificates >/dev/null
curl --fail --silent --show-error --retry 15 --retry-connrefused --retry-delay 1 --location https://acme-v02.api.letsencrypt.org/directory >/dev/null
echo 'Isolated DNS and ACME ready. Real challenge validation is enabled.'
