# PN51 Ansible

Run from the repository root after Terraform has created the four guests and
you have verified their SSH host fingerprints through the Proxmox console.

```bash
make setup
make inventory
make vault
make configure
make verify
make idempotence
```

The root Ansible configuration selects the ignored generated JSON inventory and
the pinned local collections. The example inventory uses documentation-only
addresses and is for offline tests, not deployment.

| Role | Ownership |
| --- | --- |
| `baseline` | Cloud-init wait, Ubuntu 26.04 VM assertions, full Desktop, guest agent, SSH, swap, modules, sysctl, security updates, no sleep |
| `dotfiles` | Optional pinned public user-environment source, lightweight node packages, official kubectl, missing plugins, content-aware configuration and backups |
| `k3s` | Checksummed binary, root-only token/config, systemd unit, single-server etcd snapshots, secure worker join, serial drained changes |
| `monitoring` | Checksummed chart, safe YAML 1.2 CRDs, existing Grafana Secret, persistent private monitoring, readiness |

Terraform owns the node addresses, pod/service CIDRs, and cluster DNS address.
Keep those values in its generated inventory; group variables do not override
them. The encrypted vault supplies the K3s token, Grafana password, and optional
desktop console password hash. No plaintext secret belongs in this directory.

For guest dotfiles, the example already pins the published revision. Copy
[config.example.yml](config.example.yml) to ignored `.local/config.yml`, and set
the desired personal/work profile. Keep the reviewed full commit SHA. Then run
from the homelab root:

```bash
make configure CONFIG_FILE=.local/config.yml
make idempotence CONFIG_FILE=.local/config.yml
```

Deployment runs as `ubuntu` except APT package installation. No controller keys,
private environment files, or kubeconfigs are copied. The role rejects a mutable
revision or an old commit without the new bootstrap interface. It uses real
configuration/plugin checks rather than rerunning full workstation setup.
Use `make kube-shell` for explicit controller-only access to the lab kubeconfig.

Workers with an old Kubernetes identity cannot silently rejoin from a fresh
disk. Use `make replace-worker NODE=pn51-worker-2`; it refuses node-local volumes
and unrelated Terraform changes before requiring explicit confirmation.

See [provisioning](../../docs/provisioning.md),
[configuration reference](../../docs/reference.md),
[operations](../../docs/operations.md), and [testing](../../docs/testing.md).

For syntax-only validation without credentials or VMs:

```bash
uv run --frozen ansible-playbook -i pn51/ansible/inventory.example.yml \
	pn51/ansible/playbook.yml --syntax-check
make lint test-templates
```
