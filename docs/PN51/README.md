# Asus PN51

| Component | Target |
| --- | --- |
| CPU | AMD Ryzen 7 5700U, 8 cores / 16 threads |
| Graphics | Integrated Radeon Vega; guests use virtual displays, not GPU passthrough |
| Network | Gigabit Ethernet, existing private LAN or VLAN |
| Memory | 32 GiB |
| Storage | 1 TB Samsung 980 NVMe |
| Hypervisor | Proxmox VE 9 on bare metal |

## Resource Budget

| Guest | Role | vCPU | RAM | Disk |
| --- | --- | --- | --- | --- |
| `pn51-server-1` | K3s control plane and embedded etcd | 2 | 6 GiB | 80 GiB |
| `pn51-worker-1` | K3s worker | 2 | 6 GiB | 80 GiB |
| `pn51-worker-2` | K3s worker | 2 | 6 GiB | 80 GiB |
| `pn51-worker-3` | K3s worker | 2 | 6 GiB | 80 GiB |

Ubuntu Desktop runs on every guest, including the control plane. The full
`ubuntu-desktop` package installs GNOME and GDM; this is not a server-only
installation with a misleading name. A cloud image is the reproducible starting
point rather than an interactive ISO installer.

The administrator can use Proxmox's virtual console. Console login remains
password-locked unless a password hash is supplied through the vault. SSH uses
your existing keys and remains password-disabled even when console login is
enabled.

The control plane is tainted to keep ordinary workloads on workers. Desktop and
monitoring consume real resources: this baseline is appropriate for learning and
small services, not four simultaneous heavy desktop sessions or large LLMs.

See [architecture](architecture-diagrams.md), [provisioning](../provisioning.md),
and [configuration reference](../reference.md).
