# Application GitOps

Ansible installs Argo CD from the checksummed official Helm chart. It also owns
Homepage, monitoring, authentication, TLS routes, network policy, and Argo CD's
bootstrap projects. Argo CD is for reviewed application workloads, not a second
reconciler for the infrastructure that installed it.

## Ownership

| Owner | Resources |
| --- | --- |
| Terraform | Host-side VM network, identities, root/data disks, and cloud-init |
| Ansible and Helm | Host/guest baseline, K3s, monitoring, Homepage, Authelia, Headlamp, Argo CD bootstrap and ingress |
| Argo CD applications | Reviewed namespaced workloads in `fitness-tracker` only |

The `default` project allows no repositories or destinations. The `homelab`
project permits only `https://github.com/TheNewThinkTank/homelab.git` and the
`fitness-tracker` namespace on this cluster. It cannot manage cluster-scoped
resources or the `platform`, `monitoring`, `argocd`, or `kube-system` namespaces.
Ansible precreates the application namespace with restricted Pod Security.

Argo CD itself remains a privileged cluster controller: protect its namespace,
administrator account, repository credentials, and project administration.
Project limits are not isolation from a compromised controller.

## Access and Authentication

Open `https://argocd.pn51.192.168.1.20.sslip.io` or use the Homepage link. Authelia
MFA protects the external route; Argo CD then requires its own login. Anonymous
Argo CD access is disabled and the default authenticated role is read-only.
The initial `admin` credential is a Kubernetes Secret, not a public Helm value
or an Ansible Vault field. Follow [Argo CD access](observability.md#argo-cd-access)
to retrieve it in your own terminal and rotate it after first use.

Traefik terminates HTTPS. The Argo CD server listens on HTTP only inside its
private namespace, behind a default-deny policy and the reviewed ingress rule.
This does not disable Kubernetes API certificate verification.

## Application Example

The bootstrap does not create an Application, enable application auto-sync, or
adopt existing infrastructure. The existing `pn51/application.yaml` example now
selects the `homelab` project. Review it before applying: it follows `HEAD` and
its explicit automated sync, self-heal, and prune settings will take effect if
you choose to install it.

The example's application Secret has empty values and is not a production secret
source. Use a dedicated encrypted-secret or external-secret workflow for real
credentials; base64 is not protection. Validate images, manifests, application
backups, and any ingress/authentication changes before enabling reconciliation.
Changes in this local checkout are not available to Argo CD until deliberately
published to the configured Git repository.

To admit a different repository or namespace, review the project template and
the corresponding Ansible group variables; do not casually widen the project
to `*`. Do not edit Ansible-owned bootstrap resources through an Application.

Run `make argocd-chart-check`, `make configure`, `make verify`, and
`make idempotence` after changing the bootstrap. Chart upgrades can change CRDs;
Helm rollback does not restore application data or reverse CRD migrations.

See [security](security.md), [architecture](PN51/architecture-diagrams.md), and
[operations](operations.md).
