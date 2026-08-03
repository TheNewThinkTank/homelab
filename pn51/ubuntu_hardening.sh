#!/usr/bin/env bash

# Basic Ubuntu hardening script.
# Run as root (sudo bash ubuntu_hardening.sh)

set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this script as root or with sudo." >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive

ensure_package() {
    local pkg="$1"
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
        apt-get update -qq
        apt-get install -y --no-install-recommends "$pkg"
    fi
}

ensure_line_in_file() {
    local line="$1"
    local file="$2"
    mkdir -p "$(dirname "$file")"
    touch "$file"
    if ! grep -Fq "$line" "$file"; then
        printf '%s\n' "$line" >> "$file"
    fi
}

ensure_fstab_entry() {
    local entry="$1"
    local fstab_file="/etc/fstab"
    if ! grep -Fq "$entry" "$fstab_file"; then
        printf '%s\n' "$entry" >> "$fstab_file"
    fi
}

echo "Starting Ubuntu hardening process..."

echo "Updating package lists..."
apt-get update -qq

# 1. System updates
echo "Installing and upgrading core packages..."
apt-get upgrade -y

# 2. Configure automatic security updates
echo "Configuring automatic security updates..."
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF

# 3. Firewall Setup (UFW)
echo "Setting up firewall..."
ensure_package ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 6443/tcp comment 'Kubernetes API'
ufw allow 2379:2380/tcp comment 'etcd client API'
ufw allow 10250/tcp comment 'Kubelet API'
ufw allow 10251/tcp comment 'kube-scheduler'
ufw allow 10252/tcp comment 'kube-controller-manager'
ufw allow 30000:32767/tcp comment 'NodePort services'
ufw --force enable

# 4. SSH hardening
echo "Hardening SSH configuration..."
ensure_package openssh-server
mkdir -p /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/99-hardening.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
PermitEmptyPasswords no
KbdInteractiveAuthentication no
X11Forwarding no
PrintMotd no
Protocol 2
AuthenticationMethods publickey
EOF

if ! grep -Eq '^[[:space:]]*Include /etc/ssh/sshd_config\.d/\*\.conf' /etc/ssh/sshd_config; then
    echo 'Include /etc/ssh/sshd_config.d/*.conf' >> /etc/ssh/sshd_config
fi
systemctl restart ssh || systemctl restart sshd

# 5. Secure shared memory
echo "Securing shared memory..."
ensure_fstab_entry 'tmpfs /run/shm tmpfs defaults,noexec,nosuid 0 0'

# 6. Set up fail2ban
echo "Installing and configuring fail2ban..."
ensure_package fail2ban
systemctl enable --now fail2ban

# 7. Disable unused services
echo "Disabling unused services..."
systemctl disable avahi-daemon cups bluetooth 2>/dev/null || true

# 8. Secure sysctl settings
echo "Configuring secure sysctl settings..."
cat > /etc/sysctl.d/99-security.conf <<'EOF'
# IP spoofing protection
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1

# Ignore ICMP broadcast requests
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Disable source packet routing
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0

# Ignore send redirects
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0

# Block SYN attacks
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_max_syn_backlog = 2048
net.ipv4.tcp_synack_retries = 2
net.ipv4.tcp_syn_retries = 5

# Log Martians
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1

# Disable IPv6 if not needed (comment out if you use IPv6)
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
net.ipv6.conf.lo.disable_ipv6 = 1
EOF
sysctl --system >/dev/null

# 9. Install security auditing tools
echo "Installing security auditing tools..."
ensure_package lynis
ensure_package rkhunter
rkhunter --update >/dev/null 2>&1 || true
rkhunter --propupd >/dev/null 2>&1 || true

# 10. Install auditd for system auditing
echo "Installing and configuring auditd..."
ensure_package auditd
systemctl enable --now auditd
cat > /etc/audit/rules.d/audit.rules <<'EOF'
-D
-b 8192
-f 1
-a always,exit -S mount -S umount2 -k mount
-w /etc/pam.d/ -p wa -k auth
-w /etc/nsswitch.conf -p wa -k auth
-w /etc/group -p wa -k user_group_modification
-w /etc/passwd -p wa -k user_group_modification
-w /etc/shadow -p wa -k user_group_modification
-w /etc/network/ -p wa -k network_modifications
-w /etc/sysconfig/network -p wa -k network_modifications
-a always,exit -F arch=b64 -S sethostname -S setdomainname -k hostname_changes
-a always,exit -F arch=b32 -S sethostname -S setdomainname -k hostname_changes
-w /etc/sudoers -p wa -k sudo_modifications
-w /etc/sudoers.d/ -p wa -k sudo_modifications
-a always,exit -F arch=b64 -S adjtimex -S settimeofday -S clock_settime -k time_changes
-a always,exit -F arch=b32 -S adjtimex -S settimeofday -S clock_settime -k time_changes
-e 2
EOF
systemctl restart auditd >/dev/null 2>&1 || true

# 11. Set up logwatch and antivirus
echo "Installing logwatch and antivirus tools..."
ensure_package logwatch
ensure_package clamav
ensure_package clamav-daemon
systemctl enable --now clamav-freshclam clamav-daemon

# 12. Secure /tmp and user accounts
echo "Securing /tmp directory and account policy..."
ensure_fstab_entry 'tmpfs /tmp tmpfs defaults,noexec,nosuid 0 0'
sed -i 's/PASS_MAX_DAYS.*/PASS_MAX_DAYS 90/' /etc/login.defs
sed -i 's/PASS_MIN_DAYS.*/PASS_MIN_DAYS 7/' /etc/login.defs
sed -i 's/PASS_WARN_AGE.*/PASS_WARN_AGE 14/' /etc/login.defs

echo "Hardening complete. Please reboot your system to apply all changes."
echo "After reboot, run 'lynis audit system' to check your security posture."
