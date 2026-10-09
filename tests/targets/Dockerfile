FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive container=docker
RUN apt-get update && apt-get install -y --no-install-recommends systemd systemd-sysv openssh-server python3 python3-apt sudo rsync ca-certificates curl gnupg ufw iproute2 procps dbus \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /root/.ssh /run/sshd \
    && chmod 700 /root/.ssh \
    && ssh-keygen -A \
    && systemctl enable ssh \
    && systemctl mask systemd-resolved.service systemd-networkd.service systemd-networkd-wait-online.service \
    && printf 'PermitRootLogin prohibit-password\nPasswordAuthentication no\n' > /etc/ssh/sshd_config.d/10-test.conf
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
