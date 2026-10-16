# Guest Baseline

The Ansible baseline role is the only supported guest-bootstrap path. Do not run
the former one-off hardening scripts over these nodes; their UFW, reverse-path
filtering, package-upgrade, and service behavior conflict with this design.

## Enforced State

- Ubuntu 26.04 x86-64 guest and minimum-memory assertions, after cloud-init.
- Full Desktop, OpenSSH, AppArmor, guest agent, and security-update packages.
- Public-key SSH only, no root SSH, low authentication-attempt limit, early
	drop-in precedence, and configuration validation before a conditional reload.
- Root-only K3s config/token and administrator kubeconfig; no token in systemd
	arguments or Terraform state.
- Persisted bridge-netfilter/overlay modules, forwarding enabled, and CNI-safe
	reverse-path filtering. Kubernetes kernel-protection defaults are explicit.
- Swap removed from active state and fstab; desktop sleep/suspend targets masked.
- Security updates enabled without automatic reboots.
- Desktop graphical target enabled; optional vaulted console password hash does
	not enable password SSH.

VM ingress is enforced by Proxmox, not by duplicating iptables policy with guest
UFW. Keep the datacenter firewall active and validate the boundary from another
machine. AppArmor remains enabled; this is not a CIS certification claim.

## How to Verify the Baseline

Run `make configure`, inspect the guests' Desktop consoles, then run
`make verify` and `make idempotence`. On each guest, inspect SSH's effective
configuration with `sudo sshd -T`, swap with `swapon --show`, and the boot target
with `systemctl get-default`.

If networking fails, inspect the exact Proxmox rules, kernel settings, CNI pods,
and routes before adding broad allow rules. If SSH hardening fails validation,
keep the existing verified connection open and repair the failing setting.

See [security boundaries](../../security.md), [testing](../../testing.md), and
[maintenance](../../operations.md).
