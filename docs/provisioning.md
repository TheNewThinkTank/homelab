# Build the Four-VM Lab

This tutorial starts with a prepared Proxmox host and ends with four Ubuntu
Desktop VMs, K3s, and private Prometheus/Grafana services. No step below is run
automatically by CI. Commands are run on your trusted administrator workstation.

## What You Need

- PN51 with 32 GiB RAM, sufficient free NVMe capacity, AMD virtualization enabled,
  and reliable wired networking.
- Proxmox VE 9 installed and patched, with a working private bridge. Back up the
  current PN51 before installing it: installation can erase existing disks.
- Four unused VM IDs and four reserved IPv4 addresses outside the DHCP pool.
- A trusted Proxmox HTTPS certificate or its CA installed on the controller.
- Terraform 1.10+, uv, Helm 3, kubectl compatible with the pinned Kubernetes
  minor, OpenSSH, Git, and Make. Gitleaks and actionlint are useful for CI checks.
- An existing SSH key loaded into `ssh-agent`. Keep its private half outside
  this repository.

The sibling dotfiles project is the source of truth for your workstation and
guest user environment. Its macOS workstation setup includes Terraform, uv,
Ansible, Helm 3, kubectl, Gitleaks, and actionlint. From the homelab checkout:

```bash
cd ../dotfiles
./bootstrap.sh --platform macos --profile personal --dry-run
./bootstrap.sh --platform macos --profile personal
cd ../homelab
```

Review and confirm its plan; this is your normal full MacBook setup, not a
reduced VM package installation. Use the work profile when appropriate. If you
already manage the controller with dotfiles, do not reinstall it just to run
homelab: check the required executable versions and run `make setup` here.

If an old Helm 4 binary shadows Helm 3, fix PATH before continuing. Check
`helm version --short` and `kubectl version --client` against the
[version reference](reference.md#versions-and-artifacts).

## Step 1: Validate the Controller

```bash
make setup
make check
```

These commands do not need a vault, Proxmox token, or reachable VMs. You should
see nine passing Terraform mock tests, Python regressions, four local template
checks, a real Helm render, and a strict documentation build.

If collection installation reports `CERTIFICATE_VERIFY_FAILED`, use a verified
host CA bundle, for example on macOS:

```bash
SSL_CERT_FILE=/etc/ssl/cert.pem UV_SYSTEM_CERTS=true make setup
```

Do not bypass certificate verification. If your organization's CA is absent,
install it through the operating system's trust workflow first.

## Step 2: Prepare Proxmox

In the Proxmox UI, confirm the node name, bridge, and storage identifiers.
The disk datastore must support VM disks. Enable **Import** content on the
file-backed image datastore; the Terraform image uses a `.qcow2` filename.

Enable the **datacenter firewall** and verify that it is active. Preserve a
working Proxmox console and management rule before changing host-level firewall
policy. Terraform only manages the four new VM firewalls, never datacenter or
host firewall rules. A VM firewall flag alone is not sufficient when the
datacenter firewall is disabled.

Create a dedicated, privilege-separated API token for Terraform. Grant VM
allocation, audit, power, console, and configuration permissions for the reserved
VM IDs, and allocation/audit permissions on the chosen datastores and bridge.
The provider's `download-url` endpoint also needs `Sys.Audit`, `Sys.Modify`, and
`Datastore.AllocateTemplate`; review those host-level privileges explicitly.
Do not use the root password or a permanent unrestricted Administrator token.
Remove bootstrap-only image-download privileges after initial provisioning if
your operational policy requires it; re-grant or import the existing image when
rebuilding from empty state.

The token owner and privilege-separated token both need the applicable ACLs.
A 403 is a permissions problem, not a reason to disable TLS. See the provider's
[authentication documentation](https://registry.terraform.io/providers/bpg/proxmox/0.116.1/docs)
and Proxmox's
[permission model](https://pve.proxmox.com/pve-docs/pve-admin-guide.html#pveum_permission_management).
Exact ACLs must be validated on your host; offline tests cannot prove them.

## Step 3: Set Private Inputs and Preview

```bash
cp pn51/terraform/terraform.tfvars.example pn51/terraform/terraform.tfvars
chmod 600 pn51/terraform/terraform.tfvars
```

Edit the private copy. Set your real LAN, gateway, trusted administrator `/32`
or subnet, Proxmox node, datastores, and SSH public key. Example addresses are not
network discovery. The default pod/service networks must also be distinct from
your VPN and other routed networks.

Load the endpoint and token into your current controller session. The following
prompts for the credential without storing it in shell history; do not run it
with shell tracing enabled:

```bash
export PROXMOX_VE_ENDPOINT='https://YOUR-VERIFIED-PROXMOX-HOST:8006/'
export PROXMOX_VE_API_TOKEN="$(uv run --frozen python -c 'import getpass; print(getpass.getpass("Proxmox API token: ")))"
make plan
```

The token format is `user@realm!token-id=secret`. A password manager can populate
the same environment variable instead. Do not put this token in tfvars, a
committed `.env`, a screenshot, a support transcript, or GitHub Actions secrets.

Inspect the plan: it should create four VMs, the base-image import, and their VM
firewall resources. It must not modify the existing host or unrelated VMs.

## Step 4: Create VMs and Verify SSH Identity

```bash
make apply
make inventory
```

Confirm Terraform's plan interactively. It downloads the fixed Ubuntu image,
checks its SHA-256, and creates each guest with static networking and your public
key. Terraform does not wait for guest-agent installation: the first Ansible run
installs and starts it after SSH becomes available.

For each VM, use the **Proxmox console** to read its SSH host fingerprint:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

From your controller, connect as `ubuntu` and compare that fingerprint before
accepting it into `known_hosts`. Do not use `StrictHostKeyChecking=no`, and do not
trust an unauthenticated `ssh-keyscan` by itself. Cloud-init supplies
passwordless sudo for this automation account; protect the corresponding key.

Check trusted connectivity after accepting all four identities:

```bash
uv run --frozen ansible k3s_cluster -m ansible.builtin.ping
```

## Step 5: Create and Back Up the Vault

```bash
make vault
```

Type the vault password directly into the terminal. The helper creates a random
K3s server token and Grafana password, passes them to `ansible-vault` through
stdin, and writes only encrypted output to `.local/vault.yml` with mode 0600.
It refuses to overwrite an existing vault. Store the password separately in a
password manager and back up the encrypted file off-host before configuring K3s.

For desktop console login, edit the vault and add `desktop_password_hash` as a
quoted SHA-512-crypt or yescrypt hash:

```bash
uv run --frozen ansible-vault edit .local/vault.yml
```

Generate the hash with a trusted local password tool such as `mkpasswd` and enter
the password interactively. Never use a plaintext password or Terraform password
input. Use the vault editor on a trusted workstation; editor swap and recovery
files can contain decrypted data. Omit the field to keep console login locked.

## Step 6: Configure Desktop, Kubernetes, and Monitoring

### Optional Guest Dotfiles

Dotfiles deployment is disabled by default. The example pins the published
dotfiles commit `b703d09fe26c5bd7e9daac92450f3c313a4c7c6a`, which includes the
homelab package set, configuration checks, and official kubectl assets. Its
[published CI run](https://github.com/TheNewThinkTank/dotfiles/actions/runs/38935900511)
passed. Keep a reviewed full commit SHA, never `main` or `HEAD`. Uncommitted
sibling changes are deliberately not copied onto guests.

```bash
cp pn51/ansible/config.example.yml .local/config.yml
chmod 600 .local/config.yml
```

Review the private copy and its personal/work profile selection. The pinned
commit is ready to use. The role uses the public dotfiles Git URL, deploys as `ubuntu`, and reads
its lightweight package list and checksum-pinned kubectl from that revision.
System hardening, Desktop installation, K3s, and monitoring remain homelab-owned.
Your controller's private environment, SSH keys, and administrator kubeconfig are
never copied to the guests. GNOME shortcuts remain a separate interactive choice.

Enable the integration with:

```bash
make configure CONFIG_FILE=.local/config.yml
```

Use the same `CONFIG_FILE` for later configuration and idempotence checks. To
keep the original cluster-only setup, omit it:

```bash
make configure
```

The playbook validates that all targets are Ubuntu 26.04 x86-64 VMs. It waits for
cloud-init before apt, installs full Desktop, disables sleep and swap, configures
SSH and kernel settings, then starts K3s on the server and joins workers
serially. The first Desktop installation can take several minutes per guest.

The server's administrator kubeconfig is copied to `.local/kubeconfig` with mode
0600 and a TLS-verified external endpoint. The controller then reconciles the
chart's CRDs and Grafana Secret and installs the monitoring chart atomically.
The token never enters a service command line or Terraform state.

## Step 7: Accept the Installation

```bash
make verify
make idempotence
```

With guest dotfiles enabled, use
`make idempotence CONFIG_FILE=.local/config.yml` so both runs cover that role.
`make kube-shell` opens an interactive controller shell with only this lab's
private kubeconfig selected. Leaving that shell restores your original context;
it does not change your global shell files or copy credentials to a VM.

`verify` checks the exact four node identities and K3s versions, Ready status,
monitoring workloads, Bound persistent volumes, Grafana database health,
Prometheus scrape targets, and the chart's Helm test. `idempotence` performs a
normal run followed by a full second run that must report zero changes and no
hidden failures on all four hosts. It can prompt for the vault password twice.

Use [monitoring access](observability.md) for loopback-only port forwarding.
Before using real workloads, configure and test [off-host backups](operations.md).

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Proxmox returns 403 | Inspect token-owner and token ACLs, storage permissions, and download privileges |
| Import fails | Enable Import content and check free space, filename, checksum, and Proxmox version |
| SSH host key is unknown | Compare through the Proxmox console; accept only the verified fingerprint |
| Cloud-init fails or apt is locked | Inspect `cloud-init status --long` and its logs; do not delete apt lockfiles |
| A target is not Ubuntu 26.04 | Stop and correct the image/inventory; do not weaken the assertion |
| Worker name already exists | Use the guarded replacement procedure, not forced node-password deletion |
| Token mismatch | Restore the original vault; do not invent a new token for the old datastore |
| Monitoring stays Pending | Check PVC binding, worker RAM/disk, local-path provisioner, and pod events |

## What You Built

You have four declaratively managed Desktop VMs, a private K3s cluster, and
persistent monitoring. Continue with [operations](operations.md),
[security](security.md), and [the reference](reference.md). The live gates are
what establish that this works on your actual PN51; offline CI alone does not.