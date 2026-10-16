# How to Operate and Rebuild the Lab

These procedures assume the [provisioning tutorial](provisioning.md) has completed
and the [live acceptance checks](testing.md) pass. Keep an independent controller
and off-host backups; the PN51 must not be its own only recovery environment.

## How to Reconcile Desired State

```bash
make plan
make configure
make verify
```

Apply Terraform only when the reviewed plan contains intended VM changes. A
normal Ansible run repairs declared package/file/service state without rebooting
or unconditionally upgrading everything. If you changed Terraform networking,
regenerate inventory and inspect connectivity before configuring guests.

Do not change node names, pod/service CIDRs, or the server token in a running
cluster as routine configuration. These values are cluster identity, not casual
tuning knobs.

## How to Replace a Worker

1. Check backups and identify the generated worker name with
   `kubectl --kubeconfig .local/kubeconfig get nodes -o wide`.
2. Run `make replace-worker NODE=pn51-worker-2`.
3. Inspect the saved Terraform plan. The helper rejects changes outside that
   worker and its firewall resources. Type the exact confirmation only when
   destroying its root disk is intended.
4. After replacement, open the new VM's Proxmox console and verify its SSH host
   fingerprint. Remove only the old address's `known_hosts` entry after confirming
   this was an expected rebuild, then accept the new verified key.
5. Run `make configure`, `make verify`, and `make idempotence`.

The helper requires the server and remaining workers to be Ready. It refuses
node-affined or uncertain local persistent volumes before draining. A released
or retained PV can still hold data and can still block replacement. It respects
pod disruption budgets and does not use forced eviction. EmptyDir data is
explicitly disposable and is deleted by drain.

After a successful Terraform replacement, it deletes the old Kubernetes Node and
waits for K3s to remove the corresponding node-password Secret. The new guest can
then rejoin with the same stable node name. Never manually erase an active
worker's identity just to make a join succeed.

### Data-Bearing Workers

The default local-path provisioner stores data under
`/var/lib/rancher/k3s/storage` on one VM. A persistent volume's node affinity
prevents it from following a pod to a different worker. Kubernetes rescheduling
is not a storage migration.

For data-bearing workers, first use a workload-specific backup/restore or migrate
to an existing off-host storage class. Verify restored data, remove obsolete
claims/PVs only when their contents are no longer needed, and rerun the guarded
procedure. Do not remove affinity or delete PVs merely to bypass its warning.

## How to Update Software

Take and verify backups first. Update one ownership layer at a time:

| Layer | Procedure |
| --- | --- |
| Controller dependencies | Review project changes, run `uv lock`, commit lockfile, run `make setup check` |
| Provider | Review release notes and planned replacements; update provider pin and lockfile; run mock tests |
| Ubuntu base image | Choose a dated official image, verify signed checksums, update URL/hash, review replacement plan |
| Ubuntu guest packages | Use a drained, one-at-a-time maintenance window for upgrades and required reboots |
| K3s | Review supported upgrade path and release checksum, change version/hash together, run offline and live tests |
| Monitoring | Review chart/Grafana/operator upgrade notes, update version/hash together, render/check CRD changes |

K3s server changes happen before workers. The single API server can be unavailable
during restart; workers are processed one at a time and drained only when their
K3s binary/config/unit changes. Existing disruption budgets can legitimately stop
an upgrade. Never bypass them without understanding the affected workload.

Guest security updates run unattended, but automatic reboots are disabled. During
maintenance, drain the selected worker, upgrade packages, reboot if required,
wait for Ready, uncordon, and verify workloads before moving to the next. A server
reboot is a planned API outage. Desktop packages are not frozen by the cloud-image
pin; current security packages come from Ubuntu's repositories.

The role reconciles chart CRDs separately with server-side apply. Conflicts are
not force-overwritten. Helm's atomic rollback does not roll back CRDs, databases,
or PVC data; follow upstream migration requirements and keep backups.

## How to Back Up

Back up these independent layers:

| Layer | Required off-host material |
| --- | --- |
| Terraform | State and backup, private tfvars/backend configuration, provider lockfile |
| Controller | Encrypted vault, separate vault password, SSH key recovery, trusted CA details |
| K3s | etcd snapshot plus the original server token and configuration |
| Applications | Database-native backups and persistent volume contents |
| Hypervisor | Proxmox configuration and tested VM backups to independent storage |

K3s takes a local embedded-etcd snapshot every six hours and retains 14. Those
snapshots are lost with the server disk unless exported. Create a manual snapshot
through the verified server SSH connection before a change:

```bash
sudo /usr/local/bin/k3s etcd-snapshot save --name before-maintenance
sudo /usr/local/bin/k3s etcd-snapshot ls
```

These are **guest commands**, not controller commands. Export snapshots from
`/var/lib/rancher/k3s/server/db/snapshots` to encrypted storage on another machine.
Protect the original token with them; losing it can make a snapshot unusable.
Configure K3s S3 snapshot support separately if you want automatic off-host
exports. This repository does not invent an S3 endpoint or silently claim
off-host backup automation.

An etcd snapshot contains Kubernetes objects, not Grafana's SQLite database,
Prometheus's TSDB, or arbitrary PV files. Quiesce or use each application's
documented backup mechanism. Use Proxmox Backup Server on independent storage for
VM-level protection where available, and test restoration into isolated VM IDs
and a non-conflicting network.

## How to Recover the Control Plane

The automated worker helper refuses the server. Server replacement needs the
original vault/token, the relevant etcd snapshot, preserved addressing, and a
separate restore window.

1. Stop the old server permanently and prevent it from coming back with the same
   address. Preserve its disk for investigation if possible.
2. Restore a tested Proxmox backup, or provision a fresh Ubuntu 26.04 guest at the
   declared identity. Verify its SSH fingerprint. Do not blindly run normal
   configuration against an empty datastore: that would create a new cluster.
3. Install the **same pinned K3s version** and baseline. Securely restore the
   original root token/config files and place the snapshot on the guest.
4. Follow the [upstream single-server snapshot restore procedure](https://docs.k3s.io/datastore/backup-restore).
   With K3s stopped, use its explicit `server --cluster-reset
   --cluster-reset-restore-path=/absolute/snapshot/path` operation, the original
   token, and the original configuration. This is a manual recovery action, not
   a normal service flag; do not leave cluster-reset in the systemd unit.
5. Start K3s normally. Verify restored node identities and resources before
   reconciling anything. Existing workers should connect to the restored API;
   investigate identities rather than deleting them blindly.
6. Export a fresh administrator kubeconfig, reconcile desired state, restore PV
   data as needed, then run `make verify` and `make idempotence`.

Keep recovery instructions matched to the pinned release and test them in an
isolated lab. A full restore has not been proven merely because an offline unit
test passes.

## How to Rebuild Everything

Take off-host backups and verify recoverability. `make destroy` requires normal
Terraform confirmation and deletes the managed VMs, their disks, and the managed
base image. Local ignored files are not automatically erased. Review the full
destroy plan before confirming.

For an intentionally empty new cluster, apply again, verify new SSH fingerprints,
and configure from the preserved private inputs. For recovery, restore etcd and
application data instead of allowing a fresh cluster to replace the old one.
Never discard Terraform state while the corresponding resources still exist:
restore the state or import the exact existing resources first.

## Troubleshooting

| Failure | Safe response |
| --- | --- |
| Drain blocked | Inspect disruption budgets and replica health; do not force eviction by default |
| Replacement stops after VM apply | Inspect saved plan/state and new VM; finish verified identity cleanup and provisioning |
| Replacement blocked by PV | Migrate or restore its data before deleting its VM |
| Node remains cordoned after interruption | Confirm node health, then explicitly uncordon it |
| API lost after server rebuild | Restore the original datastore/token; do not join workers to an unintended new cluster |
| Helm upgrade rollback fails | Inspect CRD and data migrations separately from release rollback |

See [security](security.md), [reference](reference.md), and
[live acceptance](testing.md).