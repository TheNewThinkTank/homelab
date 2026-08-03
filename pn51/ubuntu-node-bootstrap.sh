#!/usr/bin/env bash

# Bootstrap a Ubuntu node for home-lab use.
# After running this script:
#   sudo hostnamectl set-hostname <name>
#   sudo vim /etc/hosts
# Reserve a DHCP address in your router (for example 192.168.1.30).

set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this script as root or with sudo." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USERNAME="${SUDO_USER:-${USER:-ubuntu}}"
HOME_DIR="/root"

if [[ "${USERNAME}" != "root" ]]; then
    HOME_DIR="/home/${USERNAME}"
fi

BASHRC="${HOME_DIR}/.bashrc"

ensure_package() {
    local pkg="$1"
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
        apt-get update -qq
        apt-get install -y --no-install-recommends "$pkg"
    fi
}

echo "==> Ubuntu node bootstrap starting..."
echo "==> Configuring user: ${USERNAME}"
echo "==> Updating package lists"
apt-get update -qq
echo "==> Upgrading installed packages"
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
echo "==> Installing base packages"
for pkg in \
    openssh-server \
    curl \
    wget \
    git \
    vim \
    nano \
    tmux \
    htop \
    btop \
    tree \
    jq \
    unzip \
    ca-certificates \
    gnupg \
    net-tools \
    dnsutils \
    traceroute \
    nmap \
    build-essential \
    python3 \
    python3-pip \
    python3-venv; do
    ensure_package "$pkg"
done

echo "==> Enabling SSH"
systemctl enable --now ssh
echo "SSH status:"
systemctl --no-pager status ssh | head -20

echo "==> Fixing SSH permissions"
if [[ -d "${HOME_DIR}/.ssh" ]]; then
    chown -R "${USERNAME}:${USERNAME}" "${HOME_DIR}/.ssh"
    chmod 700 "${HOME_DIR}/.ssh"

    if [[ -f "${HOME_DIR}/.ssh/authorized_keys" ]]; then
        chmod 600 "${HOME_DIR}/.ssh/authorized_keys"
    fi
fi

echo "==> Adding useful aliases"
touch "${BASHRC}"
if ! grep -q "bootstrap aliases" "${BASHRC}"; then
    cat <<'EOF' >> "${BASHRC}"

# bootstrap aliases
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'
alias k='kubectl'
alias d='docker'

EOF
fi

echo "==> Enabling time synchronisation"
if command -v timedatectl >/dev/null 2>&1; then
    timedatectl set-ntp true
fi

echo "==> Disabling automatic sleep"
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null || true

echo "==> Applying hardening baseline"
if [[ -x "${SCRIPT_DIR}/ubuntu_hardening.sh" ]]; then
    bash "${SCRIPT_DIR}/ubuntu_hardening.sh"
else
    echo "Hardening script not found at ${SCRIPT_DIR}/ubuntu_hardening.sh" >&2
    exit 1
fi

echo
echo "======================================"
echo " Bootstrap complete"
echo "======================================"
echo
echo "Hostname:"
hostname
echo
echo "IP addresses:"
hostname -I
echo
echo "SSH:"
systemctl status ssh --no-pager | head -10
echo
echo "Next recommended steps:"
echo "1. Create DHCP reservation in router"
echo "2. Reboot"
echo "3. Verify SSH from another machine"
echo "4. Install Docker/Kubernetes tooling"
echo
