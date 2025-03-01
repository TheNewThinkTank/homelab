## Check Flux Sync

Trigger a manual Flux reconciliation to ensure all the changes are applied:

```bash
flux reconcile kustomization flux-system -n flux-system

# Verify that the HelmRepository and HelmReleases are correctly deployed
flux get helmrepositories -n flux-system
flux get helmreleases -n monitoring
```
