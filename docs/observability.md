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
