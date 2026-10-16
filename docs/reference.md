# Configuration and Command Reference

Run commands from the repository root. Relative inventory, role, collection,
and local-artifact paths depend on that working directory.

## Versions and Artifacts

| Component | Pin or supported range | Location |
| --- | --- | --- |
| Proxmox VE | 9.x prerequisite | Existing hypervisor; not installed by automation |
| Terraform | `>= 1.10, < 2`; CI uses `1.16.6` | Terraform required-version constraint |
| Proxmox provider | `bpg/proxmox` `0.116.1` | Terraform versions and provider lockfile |
| Ubuntu base | 26.04 amd64, build `20260927` | Terraform image URL and SHA-256 |
| Desktop | Full `ubuntu-desktop` metapackage | Baseline role; current packages from Ubuntu repositories |
| K3s | `v1.37.1+k3s1` | Ansible group variables; binary SHA-256 |
| Helm | 3.x; CI uses `3.22.1` | Local CLI and CI setup |
| Monitoring chart | `92.9.0` | Ansible group variables; archive SHA-256 |
| Python | 3.13 or 3.14; CI uses 3.13 | Project constraint and `uv.lock` |
| Ansible | Core `2.20.6` | Project dependencies and `uv.lock` |
| Collections | `ansible.posix` `2.1.0`, `kubernetes.core` `6.1.0` | Ansible requirements |

Image and binary pins are immutable inputs, not permission to ignore security
updates. Ubuntu's package repositories evolve; package installation is
convergent, not a bit-for-bit image build. Review and update version/checksum
pairs together, commit lockfiles, then run all tests and the live gates.

## Terraform Inputs

Copy the example into ignored `pn51/terraform/terraform.tfvars` and replace its
public-key placeholder. It is deliberately invalid until a real public key is
provided.

| Input | Type | Default | Constraint or behavior |
| --- | --- | --- | --- |
| `proxmox_node` | string | required | Existing Proxmox node name |
| `network_cidr` | string | required | Canonical IPv4 LAN/VLAN subnet |
| `gateway` | string | required | Usable address inside the node subnet |
| `admin_cidrs` | set(string) | required | Trusted IPv4 networks; no `/0` |
| `ssh_public_keys` | list(string) | required | OpenSSH public keys, not paths or private keys |
| `vm_datastore` | string | `local-lvm` | Supports VM and cloud-init disks |
| `image_datastore` | string | `local` | File-backed; enable Import content |
| `bridge` | string | `vmbr0` | Pre-existing private bridge |
| `cluster_name` | string | `pn51` | 2-32 lowercase DNS-safe characters |
| `vm_id_start` | number | `5100` | Integer 100-999999996; reserves four consecutive IDs |
| `node_ip_offset` | number | `40` | Four usable consecutive addresses, excluding gateway |
| `dns_servers` | list(string) | `1.1.1.1`, `9.9.9.9` | At least one reachable IPv4 resolver |
| `vm_memory_mb` | number | `6144` | Integer, at least 6144; multiplied by four |
| `vm_disk_gb` | number | `80` | Integer, at least 48; disks cannot be shrunk safely |
| `pod_cidr` | string | `10.42.0.0/16` | IPv4 prefix at most `/22`; immutable on a running cluster |
| `service_cidr` | string | `10.43.0.0/16` | IPv4 prefix at most `/24`; immutable on a running cluster |

The node, pod, and service networks must not overlap. Check router, VPN, and
remote-site networks too: Terraform cannot discover your external routing table.
Keep guest addresses outside DHCP and reserve IDs before the first apply.

Changing the cluster name, network identity, imported base image, or disk inputs
can be destructive or require an explicit rebuild. Always inspect the plan.

### Outputs

`nodes` maps stable names to VM IDs, roles, and addresses. `ansible_inventory`
contains one `k3s_server`, three `k3s_agents`, SSH username, guest Python path,
cluster CIDRs, and the service subnet's host-10 DNS address. Neither output
contains passwords, private keys, Kubernetes tokens, or kubeconfig data.

## Controller Environment

| Variable | Purpose |
| --- | --- |
| `PROXMOX_VE_ENDPOINT` | Verified HTTPS URL, including port 8006 |
| `PROXMOX_VE_API_TOKEN` | Dedicated API credential in provider format `user@realm!token=secret` |
| `ANSIBLE_CONFIG` | Normally unset; the root configuration is selected automatically |
| `ANSIBLE_VAULT_PASSWORD_FILE` | Optional absolute path outside Git; mode 0600 |
| `SSL_CERT_FILE` | Optional verified CA bundle for Python tooling behind a private CA |
| `UV_SYSTEM_CERTS=true` | Use system trust when installing controller tools behind a private CA |

Never set provider insecure mode, disable SSH host checks, or turn off Kubernetes
TLS validation to get past a trust failure. Install the correct CA or verify the
host fingerprint instead.

## Vault Schema

`make vault` generates and encrypts these fields without writing plaintext:

| Key | Requirement |
| --- | --- |
| `k3s_token` | 64 lowercase hexadecimal characters; preserve the original for restore |
| `grafana_admin_password` | At least 24 characters; generated value is longer |
| `desktop_password_hash` | Optional SHA-512-crypt (`$6$`) or yescrypt (`$y$`) hash |

The desktop password hash enables console login only. Without it, Desktop still
boots, but the `ubuntu` password remains locked. Grafana's secret is a bootstrap
credential: changing it does not reset an already-initialized Grafana database.

## Commands

| Command | Effect | Live resources? |
| --- | --- | --- |
| `make setup` | Install frozen Python dependencies and pinned local collections | No |
| `make init` | Initialize Terraform provider/backend | No mutation of VMs |
| `make plan` | Refresh and preview VM changes | Reads Proxmox |
| `make apply` | Apply after Terraform confirmation | Yes |
| `make inventory` | Validate Terraform outputs and write private JSON inventory | Reads state |
| `make vault` | Prompt for vault password and create encrypted credentials | No |
| `make configure` | Reconcile Desktop, K3s, kubeconfig, and monitoring | Yes |
| `make kube-shell` | Open a controller shell with this lab's kubeconfig selected | No mutation of cluster resources |
| `make verify` | Check nodes, versions, workloads, PVCs, health, scrape targets, Helm test | Read checks plus temporary Helm test pod |
| `make idempotence` | Apply once, then require zero changes on a full second run | Yes |
| `make replace-worker NODE=pn51-worker-2` | Plan, guard, confirm, drain, and replace only that worker | Yes; destroys its root disk |
| `make destroy` | Destroy managed VMs, disks, and image after confirmation | Yes; destructive |
| `make lint` | Terraform formatting, Ruff, and production Ansible lint | No |
| `make chart-check` | Verify checksum, lint/render real chart, parse CRDs | No |
| `make test-templates` | Render actual Ansible templates twice for four fake guests | No |
| `make test` | Mocked Terraform, chart, template, and Python tests | No |
| `make check` | Lint, tests, and strict documentation build | No |
| `make secrets-scan` | Redacted Gitleaks scan of Git history | No |
| `make docs` / `make docs-serve` | Build / preview documentation | No |

`VAULT_FILE` defaults to `.local/vault.yml`. `VAULT_ARGS` defaults to
`--ask-vault-pass`; a password-file workflow can use
`make configure VAULT_ARGS='--vault-password-file /absolute/private/path'`.
`CONFIG_FILE` is unset by default; set it to `.local/config.yml` for optional
non-secret Ansible settings. Both configuration and idempotence runs use the same
file. Secret values still belong in the encrypted vault, not Make arguments.
`UV` can select a different uv executable. Do not put secret values in Make
arguments or extra-vars strings.

## Optional Dotfiles

The sibling dotfiles repository owns user configuration and its node package
manifest. Homelab fetches a pinned public commit and delegates configuration to
that repository; it does not copy workstation dotfiles or private overrides.

| Variable | Default | Contract |
| --- | --- | --- |
| `dotfiles_enabled` | `false` | Enable explicitly through your private configuration |
| `dotfiles_repository` | Public TheNewThinkTank dotfiles HTTPS Git URL | Credential-free GitHub URL |
| `dotfiles_revision` | `b703d09fe26c5bd7e9daac92450f3c313a4c7c6a` | Reviewed full lowercase 40-character published commit SHA |
| `dotfiles_profile` | `personal` | `personal` or `work`; independent of package selection |
| `dotfiles_home` | `/home/ubuntu` | Guest account boundary; the role rejects another home |
| `dotfiles_checkout` | `/home/ubuntu/.local/share/dotfiles/source` | User-owned source, never root's personal configuration |

The role requires the new `--check` and `--package-set` interfaces from the
selected commit and always selects the lightweight `homelab` package set. It
does not invoke a full workstation package installer on every run. Ansible owns
APT convergence; dotfiles owns the package names, plugins, configuration,
backup/restore, and official kubectl version/checksums.

kubectl is downloaded directly from `dl.k8s.io`, verified by SHA-256, and checked
against its declared version. The selected client must be within one Kubernetes
minor of K3s. An existing unrelated user-local binary is preserved and causes a
clear failure rather than a silent replacement. Updating the pin may require an
explicit, backed-up binary migration.

Configuration and plugin checks return 0 when current, 3 when changes are needed,
and another nonzero status on errors. Ansible installs only missing plugins and
deploys configuration only after a real content difference. An unchanged second
run creates no new configuration backups. Full live acceptance remains required.

## Monitoring Budget

| Component | CPU request | Memory request / limit | Persistent storage |
| --- | --- | --- | --- |
| Prometheus | 250m | 768 MiB / 2 GiB | 12 GiB; 3 days or 8 GB retention |
| Grafana | 100m | 128 MiB / 512 MiB | 2 GiB |
| Alertmanager | 25m | 64 MiB / 256 MiB | 1 GiB |
| Operator | 100m | 128 MiB / 256 MiB | None |
| kube-state-metrics | 50m | 64 MiB / 256 MiB | None |
| Node exporter, per node | 25m | 32 MiB / 128 MiB | None |

Grafana sidecars and chart jobs add small extra requests. The storage class is
`local-path` unless the non-secret Ansible variable `monitoring_storage_class`
selects an existing class. This does not install NFS, CSI, external storage, or
backups for you.

See [provisioning](provisioning.md), [operations](operations.md), and
[monitoring access](observability.md).