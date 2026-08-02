#!/usr/bin/env bash

# 
# The script disables password SSH login. Before running that section, make sure:
# cat ~/.ssh/authorized_keys
# exists on the node.
# 
# 
# After running this script,
# 
# sudo hostnamectl set-hostname <e.g. asus-pn51>
# 
# Then update:
# sudo vim /etc/hosts
# with
# e.g. 127.0.1.1 asus-pn51
# 
# Reserve the DHCP address
#
# e.g. asus-pn51 → 192.168.1.30
# or raspberry-pi → 192.168.1.40
#

set -euo pipefail

echo "==> Ubuntu node bootstrap starting..."

# ------------------------------------------------------------
# Basic variables
# ------------------------------------------------------------

USERNAME="${SUDO_USER:-$USER}"

echo "==> Configuring user: ${USERNAME}"

# ------------------------------------------------------------
# Update system
# ------------------------------------------------------------

echo "==> Updating package lists"

apt update

echo "==> Upgrading installed packages"

DEBIAN_FRONTEND=noninteractive apt full-upgrade -y


# ------------------------------------------------------------
# Install common tools
# ------------------------------------------------------------

echo "==> Installing base packages"

apt install -y \
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
    python3-venv


# ------------------------------------------------------------
# Enable SSH server
# ------------------------------------------------------------

echo "==> Enabling SSH"

systemctl enable --now ssh

echo "SSH status:"
systemctl --no-pager status ssh | head -20


# ------------------------------------------------------------
# SSH hardening basics
# ------------------------------------------------------------

echo "==> Applying SSH configuration"

SSHD_CONFIG="/etc/ssh/sshd_config"

# Disable password login if SSH keys are already configured.
# Comment this out if you still need password-based SSH.
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' \
    "${SSHD_CONFIG}"

sed -i 's/^#\?PubkeyAuthentication .*/PubkeyAuthentication yes/' \
    "${SSHD_CONFIG}"

systemctl restart ssh


# ------------------------------------------------------------
# User SSH directory permissions
# ------------------------------------------------------------

echo "==> Fixing SSH permissions"

if [ -d "/home/${USERNAME}/.ssh" ]; then
    chown -R "${USERNAME}:${USERNAME}" "/home/${USERNAME}/.ssh"
    chmod 700 "/home/${USERNAME}/.ssh"

    if [ -f "/home/${USERNAME}/.ssh/authorized_keys" ]; then
        chmod 600 "/home/${USERNAME}/.ssh/authorized_keys"
    fi
fi


# ------------------------------------------------------------
# Useful shell settings
# ------------------------------------------------------------

echo "==> Adding useful aliases"

BASHRC="/home/${USERNAME}/.bashrc"

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


# ------------------------------------------------------------
# Time synchronisation
# ------------------------------------------------------------

echo "==> Enabling time synchronisation"

timedatectl set-ntp true


# ------------------------------------------------------------
# Firewall
# ------------------------------------------------------------

echo "==> Configuring firewall"

apt install -y ufw

ufw allow ssh
ufw --force enable


# ------------------------------------------------------------
# Disable unnecessary sleep (desktop -> server behaviour)
# ------------------------------------------------------------

echo "==> Disabling automatic sleep"

systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target


# ------------------------------------------------------------
# Network information
# ------------------------------------------------------------

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
