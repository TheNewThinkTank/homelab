#!/usr/bin/env bash

# Basic Ubuntu Hardening Script
# Run as root (sudo bash ubuntu_hardening.sh)

# Set script to exit on error
set -e

echo "Starting Ubuntu hardening process..."

# 1. System Updates
echo "Updating system packages..."
apt update && apt upgrade -y
apt install -y unattended-upgrades apt-listchanges

# Configure automatic security updates
echo "Configuring automatic security updates..."
cat > /etc/apt/apt.conf.d/20auto-upgrades << EOF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF

# 2. Firewall Setup (UFW)
echo "Setting up firewall..."
apt install -y ufw
ufw default deny incoming
ufw default allow outgoing
# Allow SSH (modify port if you've changed the default SSH port)
ufw allow 22/tcp
# If you're running K8s, you'll need to allow those ports too
# Common K8s ports - adjust based on your specific setup
ufw allow 6443/tcp  # K8S API server
ufw allow 2379:2380/tcp  # etcd server client API
ufw allow 10250/tcp  # Kubelet API
ufw allow 10251/tcp  # kube-scheduler
ufw allow 10252/tcp  # kube-controller-manager
# If you're exposing services via NodePort
ufw allow 30000:32767/tcp
# Enable firewall
ufw --force enable

# 3. SSH Hardening
echo "Hardening SSH configuration..."
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak
sed -i 's/#PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/X11Forwarding yes/X11Forwarding no/' /etc/ssh/sshd_config
echo "Protocol 2" >> /etc/ssh/sshd_config
systemctl restart sshd

# 4. Secure shared memory
echo "Securing shared memory..."
echo "tmpfs     /run/shm     tmpfs     defaults,noexec,nosuid     0     0" >> /etc/fstab

# 5. Set up fail2ban to protect against brute force attacks
echo "Installing and configuring fail2ban..."
apt install -y fail2ban
systemctl enable fail2ban
systemctl start fail2ban

# 6. Disable unused services
echo "Disabling unused services..."
systemctl disable avahi-daemon cups bluetooth

# 7. Secure sysctl settings
echo "Configuring secure sysctl settings..."
cat > /etc/sysctl.d/99-security.conf << EOF
# IP Spoofing protection
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
sysctl -p /etc/sysctl.d/99-security.conf

# 8. Install and configure Lynis for security auditing
echo "Installing Lynis security auditing tool..."
apt install -y lynis

# 9. Install and configure Rootkit Hunter
echo "Installing Rootkit Hunter..."
apt install -y rkhunter
rkhunter --update
rkhunter --propupd

# 10. Install auditd for system auditing
echo "Installing and configuring auditd..."
apt install -y auditd
systemctl enable auditd
systemctl start auditd

# 11. Set up basic audit rules
cat > /etc/audit/rules.d/audit.rules << EOF
# Delete all existing rules
-D

# Buffer Size
-b 8192

# Failure Mode
-f 1

# Monitor file system mounts
-a always,exit -S mount -S umount2 -k mount

# Monitor changes to authentication configuration
-w /etc/pam.d/ -p wa -k auth
-w /etc/nsswitch.conf -p wa -k auth

# Monitor user/group changes
-w /etc/group -p wa -k user_group_modification
-w /etc/passwd -p wa -k user_group_modification
-w /etc/shadow -p wa -k user_group_modification

# Monitor network configuration changes
-w /etc/network/ -p wa -k network_modifications
-w /etc/sysconfig/network -p wa -k network_modifications

# Monitor changes to hostname
-a always,exit -F arch=b64 -S sethostname -S setdomainname -k hostname_changes
-a always,exit -F arch=b32 -S sethostname -S setdomainname -k hostname_changes

# Monitor sudo usage
-w /etc/sudoers -p wa -k sudo_modifications
-w /etc/sudoers.d/ -p wa -k sudo_modifications

# Monitor changes to system time
-a always,exit -F arch=b64 -S adjtimex -S settimeofday -S clock_settime -k time_changes
-a always,exit -F arch=b32 -S adjtimex -S settimeofday -S clock_settime -k time_changes

# Make the configuration immutable - requires reboot to change audit rules
-e 2
EOF

# Restart auditd to apply new rules
systemctl restart auditd

# 12. Set up logwatch for log monitoring
echo "Installing logwatch for log monitoring..."
apt install -y logwatch

# 13. Secure /tmp directory
echo "Securing /tmp directory..."
echo "tmpfs /tmp tmpfs defaults,noexec,nosuid 0 0" >> /etc/fstab

# 14. Secure user accounts
echo "Securing user accounts..."
# Set password expiration policy
sed -i 's/PASS_MAX_DAYS.*/PASS_MAX_DAYS 90/' /etc/login.defs
sed -i 's/PASS_MIN_DAYS.*/PASS_MIN_DAYS 7/' /etc/login.defs
sed -i 's/PASS_WARN_AGE.*/PASS_WARN_AGE 14/' /etc/login.defs

# 15. Install ClamAV antivirus
echo "Installing ClamAV antivirus..."
apt install -y clamav clamav-daemon
systemctl enable clamav-freshclam
systemctl start clamav-freshclam
systemctl enable clamav-daemon
systemctl start clamav-daemon

echo "Hardening complete! Please reboot your system to apply all changes."
echo "After reboot, run 'lynis audit system' to check your security posture."
