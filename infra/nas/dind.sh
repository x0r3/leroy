#!/bin/sh
set -eu
# These rules apply inside the dedicated nested daemon's network namespace.
# The NAS's own Docker/firewall configuration is never altered.
# The registry uses an address outside the nested network's dynamic pool.
# Docker regenerates /etc/hosts on container restart, so restore the daemon's
# registry lookup before accepting builds.
if ! grep -q '^10\.234\.98\.2[[:space:]]\+registry$' /etc/hosts; then
  printf '\n10.234.98.2 registry\n' >> /etc/hosts
fi
dockerd-entrypoint.sh "$@" &
daemon=$!
trap 'kill -TERM "$daemon"; wait "$daemon" || true' TERM INT
attempts=0
until docker info >/dev/null 2>&1; do
  attempts=$((attempts + 1))
  [ "$attempts" -lt 90 ] && kill -0 "$daemon" || exit 1
  sleep 1
done
iptables -N LEROY-PARITY-EGRESS
iptables -A LEROY-PARITY-EGRESS -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
iptables -A LEROY-PARITY-EGRESS -d 10.233.98.0/24 -j RETURN
iptables -A LEROY-PARITY-EGRESS -d 10.234.0.0/16 -j RETURN
iptables -A LEROY-PARITY-EGRESS -d 10.232.98.10 -p tcp --dport 8088 -j RETURN
# Only the owned VM SSH bridge; other NAS ports remain blocked.
iptables -A LEROY-PARITY-EGRESS -d 10.232.98.11 -p tcp --dport 12225 -j RETURN
for destination in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 87.106.133.233/32 213.165.73.233/32; do
  iptables -A LEROY-PARITY-EGRESS -d "$destination" -j REJECT
done
iptables -A LEROY-PARITY-EGRESS -j RETURN
iptables -I DOCKER-USER 1 -j LEROY-PARITY-EGRESS
iptables -I OUTPUT 1 -j LEROY-PARITY-EGRESS
touch /run/leroy-isolation-ready
wait "$daemon"
