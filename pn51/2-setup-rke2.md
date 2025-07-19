# Setup RKE2

[RKE2 Quickstart](https://docs.rke2.io/install/quickstart)

```bash
sudo -i

curl -sfL https://get.rke2.io | sh -

systemctl enable rke2-server.service

# hangs
systemctl start rke2-server.service

journalctl -u rke2-server -f
```

log sample output:

```bash
server is not ready: \"overlayfs\" snapshotter cannot be enabled for \"/var/lib/rancher/rke2/agent/containerd\", try using \"fuse-overlayfs\" or \"native\": failed to mount overlay: invalid argument"
```

`/etc/rancher/rke2/config.yaml`:
```bash
write-kubeconfig-mode: "0644"
node-taint:
  - "NoSchedule"
containerd_snapshots: fuse-overlayfs
# containerd:
#   config-overrides:
#     plugins."io.containerd.snapshotter.v1.overlayfs".force: false
#     plugins."io.containerd.snapshotter.v1.native".force: true
```
