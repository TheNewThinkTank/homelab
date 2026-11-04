# Guest Baseline

The Ansible baseline role is the only supported guest-bootstrap path. Do not run
the former one-off hardening scripts over these nodes; their UFW, reverse-path
filtering, package-upgrade, and service behavior conflict with this design.

## Enforced State

- Ubuntu 26.04 x86-64 guest and minimum-memory assertions, after cloud-init.
- Lean server packages, OpenSSH, AppArmor, guest agent, and security updates.
- Public-key SSH only, no root SSH, low authentication-attempt limit, early
	drop-in precedence, and configuration validation before a conditional reload.
- Root-only K3s config/token and administrator kubeconfig; no token in systemd
	arguments or Terraform state.
- Persisted bridge-netfilter/overlay modules, forwarding enabled, and CNI-safe
	reverse-path filtering. Kubernetes kernel-protection defaults are explicit.
- Swap removed from active state and fstab; sleep/suspend targets masked.
- Security updates enabled without automatic reboots.
- Server boot target and a separate protected ext4 data disk; existing signatures
	are checked before a blank disk is formatted.

VM ingress uses a dedicated default-drop nftables input table, not guest UFW or
a flush of Kubernetes forwarding tables. Retained storage and etcd snapshots
use the data disk. Validate network boundaries from another machine. AppArmor
remains enabled; this is not a CIS certification claim.

## How to Verify the Baseline

Run `make configure`, inspect the guest services and data mounts, then run
`make verify` and `make idempotence`. On each guest, inspect SSH's effective
configuration with `sudo sshd -T`, swap with `swapon --show`, and the boot target
with `systemctl get-default`.

If networking fails, inspect the owned nftables rules, kernel settings, CNI pods,
and routes before adding broad allow rules. If SSH hardening fails validation,
keep the existing verified connection open and repair the failing setting.

See [security boundaries](../../security.md), [testing](../../testing.md), and
[maintenance](../../operations.md).
