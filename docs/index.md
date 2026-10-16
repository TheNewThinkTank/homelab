# PN51 Homelab

Terraform creates four Ubuntu 26.04 LTS guests on Proxmox. Ansible installs
Ubuntu Desktop, configures a one-server/three-worker K3s cluster, and deploys
Prometheus and Grafana through the pinned `kube-prometheus-stack` Helm chart.

Start with [provisioning](provisioning.md). For an existing installation, use
[operations](operations.md) or [monitoring](observability.md).

| Need | Guide |
| --- | --- |
| Build the lab from a prepared host | [Provisioning tutorial](provisioning.md) |
| Understand ownership and failure modes | [Architecture](PN51/architecture-diagrams.md) |
| Look up inputs, versions, and commands | [Reference](reference.md) |
| Replace a worker or restore state | [Operations](operations.md) |
| Keep a public repository safe | [Security](security.md) |
| Check correctness and convergence | [Testing](testing.md) |

## Boundaries

The PN51 has 32 GiB RAM and a 1 TB NVMe disk. Four 6 GiB desktop VMs leave
8 GiB for Proxmox. Each VM has two vCPUs and an 80 GiB root disk.

This is one physical failure domain. The control plane uses a single-member
embedded etcd datastore for snapshots, not for high availability. Monitoring uses
node-local persistent volumes by default. Back up both cluster state and
application data outside this machine.
