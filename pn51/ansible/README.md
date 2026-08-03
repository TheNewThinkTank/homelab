# Ansible bootstrap for PN51

This directory contains a simple Ansible playbook for provisioning Ubuntu nodes used in the homelab.

## Usage

1. Review or update [hosts.yml](hosts.yml) with the target node IP and username.
2. Run:

```bash
ansible-playbook -i ansible/hosts.yml ansible/playbook.yml
```

## Notes

- The playbook mirrors the core steps from the shell scripts: package installation, SSH hardening, UFW, fail2ban, sysctl tuning, and basic auditing tools.
- If the target node is not reachable yet, you may need to add the SSH key first or adjust the inventory.
