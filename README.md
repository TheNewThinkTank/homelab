# homelab

My home setup running k8s on raspberry pi.

[references](docs/references.md)


## Check Flux Sync

Trigger a manual Flux reconciliation to ensure all the changes are applied:

```bash
flux reconcile kustomization flux-system -n flux-system

# Verify that the HelmRepository and HelmReleases are correctly deployed
flux get helmrepositories -n flux-system
flux get helmreleases -n monitoring
```

## Verify Prometheus and Grafana Installation

Check pods in monitoring namespace to confirm that Prometheus and Grafana are running:

```bash
kubectl get pods -n monitoring

# Check services to get the NodePort for accessing Prometheus and Grafana
kubectl get services -n monitoring
```

Use the NodePort to access Prometheus or Grafana in browser, e.g.:

**Prometheus**: `http://<z-pi-ip>:<prometheus-nodeport>`
**Grafana**: `http://<z-pi-ip>:<grafana-nodeport>`
