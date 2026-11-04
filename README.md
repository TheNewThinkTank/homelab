# PN51 Homelab

Four replaceable Ubuntu Server 26.04 LTS VMs on an Asus PN51, managed by
Terraform and Ansible. K3s runs one control plane and three workers;
`kube-prometheus-stack` adds Prometheus, Grafana, Alertmanager, dashboards,
and exporters. Traefik provides HTTPS ingress, Authelia protects dashboards
with two-factor authentication, and Headlamp provides a read-only Kubernetes UI.
Homepage is the service dashboard; Argo CD reconciles only explicitly admitted
application workloads, not the Ansible-managed platform.

| Layer | Implementation |
| --- | --- |
| Host | Ubuntu Desktop 26.04 LTS with Ansible-managed KVM/libvirt |
| Guests | Four pinned Ubuntu Server cloud images with cloud-init |
| Capacity | 2 vCPU, 4 GiB RAM, 64 GiB root + 64 GiB protected data disk per VM |
| Cluster | Checksummed K3s binary, embedded etcd, encrypted Kubernetes Secrets |
| Access | Private NAT network, verified SSH jump host, loopback API tunnel, HTTPS dashboard ingress |
| Credentials | Ansible Vault, Argon2id passwords, internal TLS, private repo-local artifacts |

**This is a single-host lab, not a highly available cluster.** Rebuilding a VM
does not preserve its root disk. Separate data disks are protected against
Terraform destruction, but remain on the same physical host. Off-host backups
are still required for hardware failure and control-plane recovery.

## Start Here

Follow [the provisioning guide](docs/provisioning.md) before applying anything.
It covers Ubuntu host reconciliation, private credentials, guest identity,
deployment, and guarded retirement of the existing host-native K3s cluster.
Run Make commands from this repo on the Mac, not from a PN51 root shell.

```bash
make setup
make init-local
make check
```

Those commands install controller tooling and run credential-free checks. They
do not create VMs. Once your private configuration is ready:

```bash
make plan
make apply
make trust-guest-keys
# Keep make tunnel running in another local terminal before configure.
make configure
make verify
make idempotence
```

Run `make host` first and enter the PN51 sudo password directly in its terminal.
After live checks pass, `make cutover CONFIRM=retire-host-k3s` creates and
verifies a cold legacy backup before publishing the VM ingress. Original host
K3s files are preserved for rollback, not silently erased.

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
- [Application GitOps and Argo CD ownership](docs/gitops.md)
- [Testing and live acceptance gates](docs/testing.md)

Preview the documentation with `make docs-serve` at <http://127.0.0.1:8000>.
`make docs` builds it in strict mode.

## Repository Layout

```text
pn51/terraform/          KVM VMs, protected data disks, NAT, cloud-init, inventory, tests
pn51/ansible/            Ubuntu host, guest baseline, K3s, monitoring, platform, cutover
pn51/monitoring/         Non-secret, resource-budgeted Helm values
pn51/gitops/             Pinned, resource-budgeted official Argo CD chart values
pn51/dev/                Optional application examples; not deployed by bootstrap
scripts/homelab.py       Validated private artifacts and guarded operations
tests/                  Python regressions and real Ansible template contracts
docs/                   MkDocs tutorial, how-tos, reference, and architecture
.local/                 Ignored inputs, credentials, PKI, images, backups, caches, evidence
```

The provider and Python lockfiles are committed. Local Terraform inputs, state,
plans, keys, kubeconfigs, and vault passwords are not. An encrypted vault can be
stored in a private backup or deliberately committed under a separate name;
plaintext credentials must never be committed.

## Verification Status

The repository has mocked Terraform tests, offline Ansible template checks,
helper regression tests, real chart rendering, lint, strict documentation builds,
and secret scanning. These do not claim a successful deployment on your hardware.
`make verify` and `make idempotence` are the required live acceptance gates.
Live provisioning has created four running VMs, verified their guest SSH keys,
and passed a no-change Terraform plan plus Ansible connectivity on every guest.
The four-node K3s platform passes live acceptance and a full unchanged second
Ansible run. A real worker root replacement rejoined successfully, preserved a
retained-disk checksum, and kept Alertmanager's original PVC. An etcd snapshot
has also been copied off-host. Legacy host K3s is now stopped and disabled; its
cold archive has a verified private off-host copy, and its original files remain
available for rollback. LAN HTTPS ingress is active with verified certificates
and anonymous dashboard requests redirecting to Authelia. Snapshot restore has
not been exercised, so the backup is not a claim of tested disaster recovery.
