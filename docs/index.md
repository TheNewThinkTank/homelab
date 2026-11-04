# PN51 Homelab

Terraform creates four Ubuntu Server 26.04 LTS VMs on the PN51's Ubuntu Desktop
KVM host. Ansible configures a one-server/three-worker K3s cluster, retained data
disks, Prometheus, Grafana, Authelia MFA, Headlamp, Homepage, scoped Argo CD,
and protected HTTPS ingress.

Start with [provisioning](provisioning.md). For an existing installation, use
[operations](operations.md) or [monitoring](observability.md).

| Need | Guide |
| --- | --- |
| Build the lab from a prepared host | [Provisioning tutorial](provisioning.md) |
| Understand ownership and failure modes | [Architecture](PN51/architecture-diagrams.md) |
| Look up inputs, versions, and commands | [Reference](reference.md) |
| Replace a worker or restore state | [Operations](operations.md) |
| Keep a public repository safe | [Security](security.md) |
| Manage application GitOps without adopting infrastructure | [Argo CD ownership](gitops.md) |
| Check correctness and convergence | [Testing](testing.md) |

## Boundaries

The PN51 has 32 GiB RAM and a 1 TB NVMe disk. Four 4 GiB server VMs leave about
half the memory for the Desktop host. Each VM has two vCPUs, a replaceable 64 GiB
root disk, and a protected 64 GiB application data disk.

This is one physical failure domain. The control plane uses a single-member
embedded etcd datastore for snapshots, not for high availability. Monitoring uses
node-local persistent volumes by default. Back up both cluster state and
application data outside this machine.
