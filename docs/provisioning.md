# Build the Four-VM Lab

Keep Ubuntu Desktop 26.04 LTS on the PN51. Terraform creates four Ubuntu Server
VMs on native KVM/libvirt; Ansible configures K3s, retained storage, monitoring,
Authelia, Headlamp, and protected HTTPS ingress.

**All Make commands below run from this repository on the Mac controller.** A
PN51 root shell is not the controller and does not contain this Makefile. No Mac
packages, shell files, routes, DNS settings, or trust-store changes are made.
Generated controller files stay under this repo's ignored `.local` directory.

## What You Need

- PN51 with 32 GiB RAM, sufficient free NVMe capacity, AMD virtualization enabled,
  and a working `ssh pn51` alias with an already verified host key.
- Ubuntu host sudo authentication supplied directly in a terminal. Ubuntu 26.04
  uses sudo-rs; do not add unsupported `timestamp_type` settings or passwordless
  host sudo just to automate setup.
- Existing Terraform 1.10+, uv, Helm 3, a compatible kubectl, OpenSSH, Git, and
  Make on the controller. No Homebrew or global Mac installation is part of this
  workflow.
- An existing PN51 SSH key; only its public half enters Terraform/cloud-init.
- A non-overlapping private subnet. The default `10.51.0.0/24` NAT network works
  over the PN51's existing Wi-Fi without replacing its LAN connection.

The live audit found Ubuntu 26.04.1, a Ryzen 7 5700U, about 31 GiB usable RAM,
and Wi-Fi address `192.168.1.20`. Reserve that address on the router or update
the SSH alias and `lab_domain` deliberately. No router configuration is changed
automatically.

## Step 1: Prepare Local Tools and Private Inputs

```bash
make setup
make init-local
make fitness-credentials
make check
```

`init-local` discovers the existing SSH public key, writes private Terraform
inputs, generates an encrypted vault and private vault-password file, and creates
an internal CA/certificate. It reuses existing credentials and PKI instead of
silently regenerating cluster identity. The ISO helper and Python dependencies
are installed only in the repo's virtual environment.

The vault password, private TLS keys, kubeconfig, and state are sensitive even
though Git ignores them. Back them up securely and store the vault password
separately in a password manager. TLS downloads use verified system trust and
pinned SHA-256 checks; never use insecure TLS flags.

The fitness credential step adds private app bootstrap fields without deploying
an Application or contacting Google. If the workload is still an unreleased
draft, run `make check ALLOW_UNRELEASED=1` here; deployment remains blocked until
the strict [application release flow](gitops.md#fitness-tracker-release) passes.

## Step 2: Reconcile the Ubuntu Host

```bash
make host
```

Enter the PN51 password at `BECOME password:` in the local task terminal, never
in chat. This installs KVM/libvirt and cloud-image tools, grants `gus` access to
system libvirt, allows guest NAT egress through UFW, and prevents host suspend.
It does not reinstall Ubuntu or stop the existing host-native K3s cluster.
New SSH sessions pick up the libvirt group membership.

The VM storage directory is owned by QEMU and the privileged libvirt group with
mode 0750; unrelated host users cannot read the guest disks. Reconcile the host
role before storing cluster credentials.

The host role selects `qemu-system-x86` explicitly. Ubuntu 26.04's `qemu-kvm`
is a virtual package with multiple providers, not an installable candidate.

Host automation explicitly uses the already installed `/usr/bin/sudo.ws`.
Ubuntu's sudo-rs wraps custom prompts, which Ansible 2.20 does not recognize;
this otherwise times out during fact gathering. The override is only in the
host inventory, does not change sudo policy or the default executable, and does
not affect guest passwordless sudo.

## Step 3: Plan and Create Four VMs

```bash
make plan
make apply
```

The plan should contain only this lab's pool, NAT network, pinned image, four
cloud-init seeds, four root disks, four protected data disks, and four domains.
Each guest gets two vCPUs and 4 GiB RAM, leaving about half the host's RAM for
Ubuntu Desktop. Root and data disks are sparse 64 GiB qcow2 volumes.

Terraform confirmation is retained. Do not apply unexpected deletions or
control-plane replacement. `prevent_destroy` on data disks deliberately blocks
a full destroy; it is not a substitute for off-host backups.

The domain transform declares concrete disk file paths and the qcow2 backing
chain so libvirt can apply its security labeling. The repo-local ISO helper
emits the pinned provider's legacy primary filenames as well as the normal guest
filenames. Guest link-local addresses remain computed observations; cloud-init
owns the declared static IPv4 addresses.

## Step 4: Verify Guest Identity and Open the API Tunnel

```bash
make trust-guest-keys
```

The helper reads public guest SSH keys through the authenticated PN51 libvirt
guest agent, checks declared MAC identities, and writes `.local/known_hosts`.
It does not trust unauthenticated keyscan output or change the Mac's global
known-hosts file. Cloud-init supplies key-only SSH and passwordless guest sudo
to the protected `ubuntu` automation account.

In another local terminal, keep this running:

```bash
make tunnel
```

The Kubernetes API is forwarded only to `127.0.0.1:16443`. No controller route
or global kubeconfig is changed. Keep the tunnel open for configure, verification,
Helm operations, and worker replacement.

The tunnel sends SSH keepalives every 30 seconds. If the SSH connection exits
after a network interruption, restart `make tunnel` before using the private API.

## Step 5: Configure the Cluster and Add-ons

```bash
make configure
make verify
make idempotence
```

Ansible waits for cloud-init, checks that targets are Ubuntu server VMs, mounts
the retained data disks, hardens SSH/kernel settings, and installs K3s. Workers
join serially with a CA-pinned token. Monitoring and Authelia use the dedicated
`homelab-retained` storage class under `/srv/homelab-data/storage`.

The controller reconciles Prometheus CRDs, vaulted Secrets, the pinned monitoring
chart, the pinned Argo CD bootstrap, Homepage, Authelia, Headlamp, ingress, and
network policies. Argo CD receives no Application automatically and its project
is limited to the reviewed repository and application namespace. Secret values are not
stored in Terraform or Helm values. `verify` checks four Ready nodes, versions,
workload health, retained PVCs, scrape targets, and essential system add-ons.
`idempotence` requires a full second guest run with zero changes or hidden failures.

Homepage is the authenticated service landing page. Argo CD retains its own
administrator login behind Authelia MFA; retrieve its initial credential only
through the [documented trusted-terminal workflow](observability.md#argo-cd-access).
Review [GitOps ownership](gitops.md) before enabling an Application.

## Optional Guest Dotfiles

Guest dotfiles remain opt-in and come from the pinned public sibling project's
published commit, never copied controller files or mutable branches:

```bash
make configure CONFIG_FILE=.local/config.yml
make idempotence CONFIG_FILE=.local/config.yml
```

Review `pn51/ansible/config.example.yml` before preparing the private config.
This role installs only the lightweight guest package set and user environment;
it does not configure the Mac. Use the same config file for both reconciliation
and idempotence.

## Step 6: Retire the Legacy Host Cluster and Publish Ingress

```bash
make cutover CONFIRM=retire-host-k3s
```

This first runs live cluster checks, cold-archives the old host cluster, verifies
an off-host copy under `.local/backups/legacy-k3s`, then enables HAProxy forwarding
to the VM ingress. The legacy files remain for rollback. Old application data is
preserved in the archive, not silently imported or discarded.

Read [legacy cutover and rollback](operations.md#legacy-cutover-and-rollback)
before confirming. Review any non-default old PV storage separately. After
cutover, use [the service access guide](observability.md) to enroll Authelia MFA
and obtain a short-lived, read-only Headlamp token in your own terminal.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| No rule for `make host` | Run from this repo on the Mac, not the PN51 root shell |
| Remote libvirt socket unavailable | Complete `make host`, then open a fresh SSH session for group membership |
| Unknown guest SSH key | Run `make trust-guest-keys`; never disable host-key checking |
| API endpoint unavailable | Keep `make tunnel` running and check local port 16443 |
| Cloud-init fails or apt is locked | Inspect `cloud-init status --long` and its logs; do not delete apt lockfiles |
| Token mismatch | Restore the original vault; do not invent a new token for the old datastore |
| PVC stays Pending | Check the retained storage class, protected disk mount, node affinity, and pod events |
| Browser certificate warning | The internal CA is not installed into the Mac trust store automatically |

Offline checks validate declarations, not a completed live migration. Only live
verification, repeated convergence, and tested data recovery establish that the
PN51 is rebuildable.