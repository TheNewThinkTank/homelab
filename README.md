# PN51 Homelab

Four replaceable Ubuntu Desktop 26.04 LTS VMs on an Asus PN51, managed by
Terraform and Ansible. K3s runs one control plane and three workers;
`kube-prometheus-stack` adds Prometheus, Grafana, Alertmanager, dashboards,
and exporters.

| Layer | Implementation |
| --- | --- |
| Host | Proxmox VE 9, installed separately on the PN51 |
| Guests | Four Ubuntu 26.04 cloud images, converted to full Desktop by Ansible |
| Capacity | 2 vCPU, 6 GiB RAM, 80 GiB disk per VM; 8 GiB RAM reserved for the host |
| Cluster | Checksummed K3s binary, embedded etcd, encrypted Kubernetes Secrets |
| Monitoring | Checksummed, pinned Helm chart; persistent storage; private services |
| Credentials | API token in the controller environment, Ansible Vault, private local artifacts |

**This is a single-host lab, not a highly available cluster.** Rebuilding a VM
does not preserve its root disk or local persistent volumes. Keep backups outside
the PN51 before treating stateful nodes as disposable.

## Start Here

Follow [the provisioning guide](docs/provisioning.md) before applying anything.
It covers the Proxmox prerequisites, trusted TLS, reserved addresses, vault,
SSH host verification, and initial deployment. Installing Proxmox can erase the
existing host; this repository never installs it automatically.

```bash
make setup
make check
```

Those commands install controller tooling and run credential-free checks. They
do not create VMs. Once your private configuration is ready:

```bash
make plan
make apply
make inventory
make vault
# Verify each guest's SSH fingerprint through the Proxmox console first.
make configure
make verify
```

Terraform apply and destroy keep their interactive confirmations. There is no
automatic infrastructure deployment from GitHub Actions.

## Shared Dotfiles

Use the sibling dotfiles project for MacBook setup and personal shell/editor
configuration. The optional Ansible dotfiles role installs its lightweight Ubuntu
node package set and official Kubernetes kubectl, using a full published commit
SHA. It never copies the controller's private environment, keys, or kubeconfig.

The example pins the published dotfiles commit `b703d09`. Copy
[the optional configuration example](pn51/ansible/config.example.yml) into
ignored `.local/config.yml`, review the selected profile, and use
`make configure CONFIG_FILE=.local/config.yml`. Include the same file in
`make idempotence`. See [the provisioning guide](docs/provisioning.md#optional-guest-dotfiles).

`make kube-shell` selects the private lab kubeconfig only for a child controller
shell, without changing your global dotfiles or Kubernetes context.

## Documentation

- [Provisioning tutorial](docs/provisioning.md)
- [Architecture and decisions](docs/PN51/architecture-diagrams.md)
- [Configuration and command reference](docs/reference.md)
- [Rebuild, upgrade, backup, and restore](docs/operations.md)
- [Public repository and secrets model](docs/security.md)
- [Monitoring access and troubleshooting](docs/observability.md)
- [Testing and live acceptance gates](docs/testing.md)

Preview the documentation with `make docs-serve` at <http://127.0.0.1:8000>.
`make docs` builds it in strict mode.

## Repository Layout

```text
pn51/terraform/          VM lifecycle, cloud-init, firewalls, inventory, mock tests
pn51/ansible/            Guest baseline, K3s, monitoring, pinned collections
pn51/monitoring/         Non-secret, resource-budgeted Helm values
pn51/dev/                Optional application examples; not deployed by bootstrap
scripts/homelab.py       Validated private artifacts and guarded operations
tests/                  Python regressions and real Ansible template contracts
docs/                   MkDocs tutorial, how-tos, reference, and architecture
.local/                 Ignored inventory, vault, kubeconfig, charts, and evidence
```

The provider and Python lockfiles are committed. Local Terraform inputs, state,
plans, keys, kubeconfigs, and vault passwords are not. An encrypted vault can be
stored in a private backup or deliberately committed under a separate name;
plaintext credentials must never be committed.

## Verification Status

The repository has mocked Terraform tests, offline Ansible template checks,
helper regression tests, real chart rendering, lint, strict documentation builds,
and secret scanning. These do not claim a successful deployment on your hardware.
`make verify` and `make idempotence` are the required live acceptance gates after
you provide a reachable Proxmox host and your private configuration.
