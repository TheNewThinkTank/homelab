# Asus PN51

| Component | Target |
| --- | --- |
| CPU | AMD Ryzen 7 5700U, 8 cores / 16 threads |
| Graphics | Integrated Radeon for the Desktop host; no guest GPU passthrough |
| Network | Existing Wi-Fi at 192.168.1.20; guest NAT does not replace the LAN interface |
| Memory | 32 GiB |
| Storage | 1 TB NVMe |
| Hypervisor | Ansible-managed KVM/libvirt on Ubuntu Desktop 26.04 LTS |

## Resource Budget

| Guest | Role | vCPU | RAM | Disk |
| --- | --- | --- | --- | --- |
| `pn51-server-1` | K3s control plane and embedded etcd | 2 | 4 GiB | 64 GiB root + 64 GiB retained |
| `pn51-worker-1` | K3s worker | 2 | 4 GiB | 64 GiB root + 64 GiB retained |
| `pn51-worker-2` | K3s worker | 2 | 4 GiB | 64 GiB root + 64 GiB retained |
| `pn51-worker-3` | K3s worker | 2 | 4 GiB | 64 GiB root + 64 GiB retained |

Ubuntu Desktop stays on the physical host. Guests run Ubuntu Server from a
checksummed cloud image with cloud-init networking, keys, and guest-agent
bootstrap. No guest GUI or interactive ISO installation is needed.

Administration uses verified SSH through the PN51 jump host and a loopback-only
API tunnel. Guest password/root SSH remain disabled. Separate protected data
disks survive worker root replacement; off-host backups are still required.

The control plane is tainted to keep ordinary workloads on workers. Monitoring,
Authelia, and Headlamp have bounded resource requests. The default leaves about
half the host memory for Ubuntu Desktop and the hypervisor.

See [architecture](architecture-diagrams.md), [provisioning](../provisioning.md),
and [configuration reference](../reference.md).
