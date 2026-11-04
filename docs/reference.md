# Configuration and Command Reference

Run commands from the repository root. Relative inventory, role, collection,
and local-artifact paths depend on that working directory.

## Versions and Artifacts

| Component | Pin or supported range | Location |
| --- | --- | --- |
| Host | Ubuntu Desktop 26.04 LTS | Ansible-managed KVM/libvirt |
| Terraform | `>= 1.10, < 2`; CI uses `1.16.6` | Terraform required-version constraint |
| libvirt provider | `dmacvicar/libvirt` `0.8.3` | Terraform versions and provider lockfile |
| Ubuntu base | 26.04 amd64, build `20260927` | Terraform image URL and SHA-256 |
| Guests | Ubuntu Server, no desktop installation | Cloud-init and guest baseline role |
| K3s | `v1.37.1+k3s1` | Ansible group variables; binary SHA-256 |
| Helm | 3.x; CI uses `3.22.1` | Local CLI and CI setup |
| Monitoring chart | `92.9.0` | Ansible group variables; archive SHA-256 |
| Authelia | `4.39.15` | Ansible group variables |
| Headlamp | `v0.35.0` | Ansible group variables |
| Homepage | `v2.7.0` | Ansible group variables; declarative platform config |
| Argo CD | Chart `10.11.7`, app `v3.5.7` | Official chart SHA-256 pin; Ansible bootstrap role |
| Python | 3.13 or 3.14; CI uses 3.13 | Project constraint and `uv.lock` |
| Ansible | Core `2.20.6` | Project dependencies and `uv.lock` |
| Collections | `ansible.posix` `2.1.0`, `kubernetes.core` `6.1.0` | Ansible requirements |

Image and binary pins are immutable inputs, not permission to ignore security
updates. Ubuntu's package repositories evolve; package installation is
convergent, not a bit-for-bit image build. Review and update version/checksum
pairs together, commit lockfiles, then run all tests and the live gates.

## Terraform Inputs

`make init-local` writes ignored `.local/terraform.tfvars.json` using the
existing PN51 SSH public key. Make passes that file explicitly. The committed
example documents overrides and deliberately contains no real key.

| Input | Type | Default | Constraint or behavior |
| --- | --- | --- | --- |
| `libvirt_uri` | string | `qemu+ssh://gus@pn51/system` | Remote system libvirt over the existing SSH identity |
| `host_ssh_alias` | string | `pn51` | Verified jump-host alias |
| `network_cidr` | string | `10.51.0.0/24` | Dedicated canonical IPv4 NAT /24 |
| `gateway` | string | `10.51.0.1` | Subnet's first usable address |
| `ssh_public_keys` | list(string) | required | OpenSSH public keys, not paths or private keys |
| `cluster_name` | string | `pn51` | 2-32 lowercase DNS-safe characters |
| `node_ip_offset` | number | `40` | Four usable consecutive addresses, excluding gateway |
| `dns_servers` | list(string) | `1.1.1.1`, `9.9.9.9` | At least one reachable IPv4 resolver |
| `vm_memory_mb` | number | `4096` | Integer 4096-6144; retain host RAM |
| `vm_vcpus` | number | `2` | Integer 2-4 per guest |
| `vm_disk_gb` | number | `64` | Sparse replaceable root disk, at least 32 GiB |
| `vm_data_disk_gb` | number | `64` | Protected retained data disk, at least 32 GiB |
| `image_path` / `image_checksum` | nullable strings | pinned manifest | Reviewed local path and SHA-256 overrides |
| `pod_cidr` | string | `10.42.0.0/16` | IPv4 prefix at most `/22`; immutable on a running cluster |
| `service_cidr` | string | `10.43.0.0/16` | IPv4 prefix at most `/24`; immutable on a running cluster |

The node, pod, and service networks must not overlap. Check router, VPN, and
remote-site networks too: Terraform cannot discover your external routing table.
The private libvirt network supplies deterministic MACs and guest addresses;
it does not reserve addresses on the physical LAN or change the Wi-Fi interface.

Changing the cluster name, network identity, imported base image, or disk inputs
can be destructive or require an explicit rebuild. Always inspect the plan.

### Outputs

`nodes` maps stable names to MACs, roles, and addresses. `ansible_inventory`
contains one `k3s_server`, three `k3s_agents`, SSH username, guest Python path,
cluster CIDRs, and the service subnet's host-10 DNS address. Neither output
contains passwords, private keys, Kubernetes tokens, or kubeconfig data.

## Controller Environment

| Variable | Purpose |
| --- | --- |
| `UV_CACHE_DIR`, `ANSIBLE_HOME`, `TMPDIR` | Make keeps generated state inside `.local` |
| `HELM_CONFIG_HOME`, `HELM_CACHE_HOME`, `HELM_DATA_HOME` | Repo-local Helm state |
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
| `authelia_password` | Generated bootstrap password; retrieve only through a trusted terminal |
| `authelia_password_hash` | Argon2id hash for the file-backed administrator |
| `authelia_session_secret` | Random 64-character hex session key |
| `authelia_storage_key` | Random 64-character hex storage encryption key |
| `authelia_jwt_secret` | Random 64-character hex identity-validation key |

Guest passwords remain locked. Grafana's secret is a bootstrap
credential: changing it does not reset an already-initialized Grafana database.

`make fitness-credentials` appends the following fields to an existing encrypted
vault without changing cluster credentials. A second run preserves them:

| Key | Requirement |
| --- | --- |
| `fitness_tracker_password` | Generated athlete password; retrieve only in a trusted terminal |
| `fitness_tracker_password_hash` | PBKDF2-SHA256 with 600,000 rounds and a random salt |
| `fitness_tracker_api_token` | Random backend/proxy token; never browser configuration |

An incomplete existing set is rejected rather than silently rotated. These
fields stay outside Git and Argo CD resource ownership.

## Commands

| Command | Effect | Live resources? |
| --- | --- | --- |
| `make setup` | Install frozen Python dependencies and pinned local collections | No |
| `make init-local` | Prepare private Terraform inputs, encrypted vault, vault password, internal PKI | No |
| `make host` | Reconcile Ubuntu KVM/libvirt, NAT egress, and host suspend policy | Yes; remote sudo prompt |
| `make image` | Download and SHA-256-verify the pinned cloud image | No |
| `make init` | Initialize Terraform provider/backend | No mutation of VMs |
| `make plan` | Refresh and preview VM changes | Reads remote libvirt |
| `make apply` | Apply after Terraform confirmation | Yes |
| `make inventory` | Validate Terraform outputs and write private JSON inventory | Reads state |
| `make vault` | Prompt for vault password and create encrypted credentials | No |
| `make fitness-credentials` | Append stable application credentials to the encrypted vault | No cluster mutation |
| `make fitness-check` | Strict manifest/image gate; optional `ALLOW_UNRELEASED=1` is draft validation only | No |
| `make fitness-deploy` | Verify published manifests, digest pins, and external Secrets; create only the Argo CD Application | Yes |
| `make trust-guest-keys` | Read verified public guest SSH keys into `.local/known_hosts` | Reads libvirt guest agents |
| `make tunnel` | Keep API forwarded to localhost:16443 | No cluster mutation |
| `make configure` | Reconcile server guests, K3s, monitoring, Homepage, Argo CD bootstrap, authentication, and ingress | Yes |
| `make cutover CONFIRM=retire-host-k3s` | Cold legacy backup, verified off-host copy, owned LAN ingress proxy | Yes; guarded legacy outage |
| `make kube-shell` | Open a controller shell with this lab's kubeconfig selected | No mutation of cluster resources |
| `make verify` | Check nodes, versions, workloads, PVCs, health, scrape targets, Helm test | Read checks plus temporary Helm test pod |
| `make idempotence` | Apply once, then require zero changes on a full second run | Yes |
| `make replace-worker NODE=pn51-worker-2` | Plan, guard, confirm, drain, and replace only that worker | Yes; destroys its root disk |
| `make destroy` | Plan full destruction; protected data disks block it | Requires separate reviewed removal of protection |
| `make lint` | Terraform formatting, Ruff, and production Ansible lint | No |
| `make chart-check` | Verify checksum, lint/render real chart, parse CRDs | No |
| `make argocd-chart-check` | Verify official chart checksum, three CRDs, private access, and application-project scope | No |
| `make test-templates` | Render actual Ansible templates twice for four fake guests | No |
| `make platform-check` | Render and validate MFA, TLS, restricted pods, RBAC, and network policies | No |
| `make test` | Mocked Terraform, chart, template, and Python tests | No |
| `make check` | Lint, tests, and strict documentation build | No |
| `make secrets-scan` | Redacted Gitleaks scan of Git history | No |
| `make docs` / `make docs-serve` | Build / preview documentation | No |

`VAULT_FILE` defaults to `.local/vault.yml`. `VAULT_ARGS` defaults to
`--vault-password-file .local/vault-password`; an operator-managed password can use
`make configure VAULT_ARGS='--vault-password-file /absolute/private/path'`.
`CONFIG_FILE` is unset by default; set it to `.local/config.yml` for optional
non-secret Ansible settings. Both configuration and idempotence runs use the same
file. Secret values still belong in the encrypted vault, not Make arguments.
`UV` can select a different uv executable. Do not put secret values in Make
arguments or extra-vars strings.

## GitOps Bootstrap Settings

| Variable | Default | Contract |
| --- | --- | --- |
| `homepage_image` | `ghcr.io/gethomepage/homepage:v2.7.0` | Version-pinned, credential-free service dashboard |
| `argocd_chart_version` | `10.11.7` | Update together with its reviewed SHA-256 |
| `argocd_namespace` | `argocd` | Trusted bootstrap/controller namespace |
| `argocd_application_namespace` | `fitness-tracker` | Only admitted application destination |
| `argocd_application_repository` | Public TheNewThinkTank homelab HTTPS Git URL | Only admitted application source; no embedded credentials |
| `fitness_tracker_enabled` | `true` | Reconcile private app credentials; does not create an Application |

Argo CD's initial administrator password is generated in Kubernetes and is not
an Ansible Vault field. Its bootstrap, CRDs, projects, and ingress remain
Ansible/Helm-owned. See [GitOps ownership](gitops.md) and
[service access](observability.md) before enabling application sync.

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
`homelab-retained` unless the non-secret Ansible variable `monitoring_storage_class`
selects an existing class. This does not install NFS, CSI, external storage, or
backups for you.

See [provisioning](provisioning.md), [operations](operations.md), and
[monitoring access](observability.md).