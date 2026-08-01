#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

swap_bytes="$(free -b | awk '/^Swap:/ {print $2}')"
if (( swap_bytes < 2147483648 )); then
  fallocate -l 2G /swapfile.alanet
  chmod 600 /swapfile.alanet
  mkswap /swapfile.alanet
  swapon /swapfile.alanet
  grep -qF '/swapfile.alanet' /etc/fstab || echo '/swapfile.alanet none swap sw 0 0' >> /etc/fstab
fi

apt-get update
apt-get install -y ca-certificates curl ufw fail2ban unattended-upgrades jq openssl

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

install -d -m 0755 /etc/docker
cat >/etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
systemctl restart docker

cat >/etc/fail2ban/jail.d/sshd.local <<'EOF'
[sshd]
enabled = true
maxretry = 5
bantime = 1h
findtime = 10m
EOF
systemctl enable --now fail2ban

ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP ACME'
ufw allow 443/tcp comment 'HTTPS'
ufw allow 8443/tcp comment 'ALANET FIN VLESS REALITY'
ufw --force enable

cat >/etc/sysctl.d/99-alanet.conf <<'EOF'
vm.swappiness=20
net.ipv4.tcp_syncookies=1
net.ipv4.conf.all.rp_filter=1
net.ipv4.conf.default.rp_filter=1
EOF
sysctl --system >/dev/null

mkdir -p /opt/alanet /opt/remnawave /opt/remnawave/subscription /opt/remnanode
chmod 700 /opt/alanet
