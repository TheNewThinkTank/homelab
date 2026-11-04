# How to Use Platform Services

The Ansible monitoring role installs a SHA-256-pinned `kube-prometheus-stack`
archive. It includes Prometheus, Grafana, Alertmanager, kube-state-metrics,
node-exporter, dashboards, rules, and Prometheus Operator CRDs.

## Prerequisites

Complete [provisioning](provisioning.md). Use the private administrator kubeconfig
on a trusted controller and keep `make tunnel` running. Services are private;
the guarded cutover adds LAN-only HTTPS access, not internet exposure.

## HTTPS and Authelia

After `make cutover CONFIRM=retire-host-k3s`, the default URLs are:

| Service | URL |
| --- | --- |
| Authelia | `https://auth.pn51.192.168.1.20.sslip.io` |
| Homepage | `https://homepage.pn51.192.168.1.20.sslip.io` |
| Argo CD | `https://argocd.pn51.192.168.1.20.sslip.io` |
| Grafana | `https://grafana.pn51.192.168.1.20.sslip.io` |
| Prometheus | `https://prometheus.pn51.192.168.1.20.sslip.io` |
| Alertmanager | `https://alertmanager.pn51.192.168.1.20.sslip.io` |
| Headlamp | `https://headlamp.pn51.192.168.1.20.sslip.io` |

Authelia's generated `gus` credential is in the encrypted vault. Retrieve it only
through your trusted terminal/password-manager workflow. MFA enrollment uses
the private filesystem notifier under Authelia's `/data/notifications.txt`;
read enrollment codes only in your own terminal, never in chat or public logs.

The internal CA is `.local/pki/ca.crt`. Nothing installs it into the Mac's trust
store. Browser trust remains an explicit operator decision; do not disable
TLS validation in provisioning. Router DNS-rebinding protection can block
sslip.io answers; a deliberately configured private DNS domain is an alternative.

## Homepage

Homepage is the default landing page after an Authelia login without a specific
return URL. It links the platform and monitoring services, including Argo CD.
Its settings and service cards are declared in the platform role's Homepage
template; edits are applied by `make configure` with a checksum-driven rollout.
It has no Kubernetes token, Docker socket, API credentials, or persistent state.
Writable cache/log files are disposable; configuration is reconstructed from Git.

## Argo CD Access

After Authelia MFA, Argo CD requires a separate login. On first installation,
retrieve its generated `admin` password only in your own trusted terminal:

```bash
kubectl --kubeconfig .local/kubeconfig -n argocd get secret argocd-initial-admin-secret \
	-o jsonpath='{.data.password}' | base64 --decode
```

Do not post the password in chat, logs, or Git. Change it in Argo CD after first
use, retain the replacement in your password manager, and remove the bootstrap
Secret once no longer needed. Its absence after rotation is normal.

The `homelab` project is restricted to the reviewed repository and
`fitness-tracker` namespace. No application is deployed or auto-synced by
bootstrap. See [GitOps ownership and the application example](gitops.md).

## Headlamp Access

In your own terminal, use the private lab kubeconfig to mint a read-only token:

```bash
kubectl --kubeconfig .local/kubeconfig -n platform create token headlamp-viewer --duration=1h
```

Enter it in Headlamp after Authelia MFA. Do not post the token in chat or store
it in Git. The default role cannot read Secrets or mutate cluster resources.
Cluster-admin access is not granted by the bootstrap.

## Fitness Tracker Access

Fitness-tracker is live at `https://fitness.pn51.192.168.1.20.sslip.io` after the
approved image/manifests release synchronized through Argo CD. Anonymous HTTPS
requests redirect to Authelia with verified lab TLS. See the
[fitness release guide](gitops.md#fitness-tracker-release) for updates.

After Authelia MFA, the application requires its own athlete sign-in. Its
generated password is in the encrypted vault's `fitness_tracker_password` field;
retrieve it only through a trusted terminal or password-manager workflow, never
in chat. The frontend keeps the backend API token server-side, and writes still
require the athlete session, a same-origin HTTPS request, and a CSRF token.

The deployment begins with empty local data. No Google Drive account, mount,
credential, or personal archive is required. New app data persists on its 2 GiB
retained SQLite claim; do not delete that claim to reset a failed rollout.

## How to Open Grafana

In a dedicated terminal:

```bash
kubectl --kubeconfig .local/kubeconfig -n monitoring port-forward \
	--address 127.0.0.1 service/monitoring-grafana 3000:80
```

Open <http://127.0.0.1:3000>. The default username is `admin`; the generated
password is in the encrypted vault. Retrieve it through your trusted local
vault workflow, not a public terminal transcript or chat. Do not bind forwarding
to `0.0.0.0`.

Dashboards supplied by the chart are available immediately. Grafana's data and
customizations persist on its 2 GiB PVC. Its admin password is initialized in the
database; changing only the bootstrap Secret does not rotate an existing account.

## How to Open Prometheus or Alertmanager

Use separate terminals as needed:

```bash
kubectl --kubeconfig .local/kubeconfig -n monitoring port-forward \
	--address 127.0.0.1 service/monitoring-prometheus 9090:9090
```

```bash
kubectl --kubeconfig .local/kubeconfig -n monitoring port-forward \
	--address 127.0.0.1 service/monitoring-alertmanager 9093:9093
```

Open <http://127.0.0.1:9090> or <http://127.0.0.1:9093>. These services have no
independent authentication boundary when bypassing ingress with administrator
port forwarding and must stay private. The LAN HTTPS routes require Authelia.
Stop each
forward with Ctrl-C when finished.

Prometheus retains up to three days or about 8 GB in a 12 GiB PVC. Its WAL and
compaction need space beyond the retention-size setting. Alertmanager uses 1 GiB
for silences and notification state. No alert email/webhook destination is
invented; configure a receiver and its credentials deliberately when required.

## How to Check Health

```bash
make verify
kubectl --kubeconfig .local/kubeconfig -n monitoring get pods,pvc,services
kubectl --kubeconfig .local/kubeconfig -n monitoring get prometheus,alertmanager
```

Expect private ClusterIP services, three Bound persistent claims, ready operator
and exporters, and ready Prometheus/Alertmanager instances. Inspect Prometheus
**Status > Targets** when a scrape fails. The workflow disables etcd,
controller-manager, scheduler, and kube-proxy monitors/rules that do not map to
this default K3s installation; it does not open their bind addresses just to make
dashboards green.

Node-exporter inspects the host but uses pod networking rather than a host
metrics listener. The monitoring namespace explicitly permits privileged pod
security for host inspection; do not admit unrelated or untrusted workloads.

## How to Change Retention or Storage

Edit the non-secret monitoring values and run `make chart-check`, then
`make configure` and `make verify`. Review the [resource reference](reference.md#monitoring-budget)
before increasing requests or retention on this 32 GiB host.

To use external storage, install and validate that storage class separately and
set the Ansible variable `monitoring_storage_class`. Changing the variable does
not migrate an existing PVC. Back up and restore data through a planned storage
migration; PVC storage class and many volume fields are immutable.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Prometheus/Alertmanager Pending | PVC binding, worker scheduling, local-path helper pod events, memory and disk |
| Grafana unavailable after restart | Its Deployment, bound PVC, node affinity, database health, and permissions |
| Targets down | Endpoint discovery, kubelet TLS/authentication, CNI traffic, and VM firewall state |
| Chart checksum mismatch | Stop; verify the reviewed version/hash pair and inspect the cached archive |
| CRD conflict on upgrade | Review upstream migrations and current field ownership; do not force conflicts blindly |
| Data unavailable after VM replacement | Check the retained data disk mount and original node name; restore from off-host backup if hardware failed |
| Old Grafana password still works | Existing database password is separate from the bootstrap Secret |

See [backup and recovery](operations.md), [security](security.md), and
[live acceptance](testing.md).
