# Threat Model

This lab assumes a trusted administrator workstation, a private trusted node
network, a patched Ubuntu KVM host, and Ubuntu/GitHub/Helm artifacts obtained through
verified TLS and pinned checksums where supported.

## What the Baseline Addresses

| Risk | Control |
| --- | --- |
| Public Git credential exposure | Ignored local artifacts, Vault, no private-key generation in Terraform, history scans |
| Accidental network exposure | Default-drop VM input, private NAT, LAN proxy ACLs, MFA-protected dashboards |
| Man-in-the-middle administration | Verified host/guest SSH keys, Kubernetes CA validation, internal HTTPS, secure worker join |
| Configuration drift | Declarative roles, handlers, mock/template tests, full live second-run acceptance |
| Unintended destructive replacement | Exact worker selection, PV guard, full-plan scope validation, typed confirmation |
| Accidental cluster identity loss | Stable inventory, stale-node detection, token mismatch guard, documented restore requirements |

## What Remains an Operator Responsibility

One machine cannot provide physical high availability. Its NVMe disk and local
volumes are not replicated. Scheduled local etcd snapshots are not off-host
backups. A compromised administrator key, Ubuntu KVM host, or cluster-admin
kubeconfig can control the lab.

Desktop remains only on the physical host. Node-exporter needs
host inspection; its namespace permits privileged pod security. VXLAN traffic is
private-network traffic, not an encrypted overlay. The cluster does not claim
universal default-deny policy for arbitrary future workloads. The platform
namespace has explicit network restrictions and the declared dashboards require
Authelia MFA; new application namespaces need their own policies.

Do not publish workloads until you have designed namespace RBAC, appropriate
NetworkPolicies, ingress TLS/authentication, dependency updates, and application
backup/restore. PodSecurityPolicy is removed from modern Kubernetes; use Pod
Security Admission and current policy tooling instead.

See the [enforced guest baseline](basic-hardening.md),
[secret and network controls](../../security.md), and
[backup/restore procedures](../../operations.md).
