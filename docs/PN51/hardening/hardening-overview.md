# Threat Model

This lab assumes a trusted administrator workstation, a private trusted node
network, a patched Proxmox host, and Ubuntu/GitHub/Helm artifacts obtained through
verified TLS and pinned checksums where supported.

## What the Baseline Addresses

| Risk | Control |
| --- | --- |
| Public Git credential exposure | Ignored local artifacts, Vault, no private-key generation in Terraform, history scans |
| Accidental network exposure | Default-drop VM ingress, explicit administrator CIDRs, no public monitoring services |
| Man-in-the-middle administration | Proxmox CA trust, verified SSH host keys, Kubernetes CA validation, secure worker join token |
| Configuration drift | Declarative roles, handlers, mock/template tests, full live second-run acceptance |
| Unintended destructive replacement | Exact worker selection, PV guard, full-plan scope validation, typed confirmation |
| Accidental cluster identity loss | Stable inventory, stale-node detection, token mismatch guard, documented restore requirements |

## What Remains an Operator Responsibility

One machine cannot provide physical high availability. Its NVMe disk and local
volumes are not replicated. Scheduled local etcd snapshots are not off-host
backups. A compromised administrator key, Proxmox host, or cluster-admin
kubeconfig can control the lab.

Desktop increases the guest package and GUI attack surface. Node-exporter needs
host inspection; its namespace permits privileged pod security. VXLAN traffic is
private-network traffic, not an encrypted overlay. The cluster does not claim
default-deny pod-to-pod policy or application-level authentication.

Do not publish workloads until you have designed namespace RBAC, appropriate
NetworkPolicies, ingress TLS/authentication, dependency updates, and application
backup/restore. PodSecurityPolicy is removed from modern Kubernetes; use Pod
Security Admission and current policy tooling instead.

See the [enforced guest baseline](basic-hardening.md),
[secret and network controls](../../security.md), and
[backup/restore procedures](../../operations.md).
