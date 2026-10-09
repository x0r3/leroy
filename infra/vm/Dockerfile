FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    qemu-system-x86 qemu-utils ovmf cloud-image-utils python3 iptables ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY launch.py /opt/leroy-vm/launch.py
ENTRYPOINT ["python3", "/opt/leroy-vm/launch.py"]
