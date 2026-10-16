# How to Use Monitoring

The Ansible monitoring role installs a SHA-256-pinned `kube-prometheus-stack`
archive. It includes Prometheus, Grafana, Alertmanager, kube-state-metrics,
node-exporter, dashboards, rules, and Prometheus Operator CRDs.

## Prerequisites

Complete [provisioning](provisioning.md). Use the private administrator kubeconfig
on a trusted controller. This is not a public dashboard installation.

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
independent public authentication boundary and must stay private. Stop each
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
| Data disappeared after VM replacement | Local-path data is on the old VM disk; restore from off-host backup |
| Old Grafana password still works | Existing database password is separate from the bootstrap Secret |

See [backup and recovery](operations.md), [security](security.md), and
[live acceptance](testing.md).
