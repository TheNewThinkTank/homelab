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

The platform bootstrap does not create an Application or adopt existing
infrastructure. The fitness-tracker workload is defined under
`pn51/dev/fitness-tracker-k8s`, and `pn51/application.yaml` selects the `homelab`
project. It follows the reviewed repository's `HEAD`; automated sync, self-heal,
and prune take effect only after the Application is deliberately created.

## Fitness Tracker Release

The cluster deployment uses the sibling application's existing backend/frontend
split. The backend has one replica, a `Recreate` rollout, and a retained local
SQLite volume at `/state`. Imported YAML is a separate read-only `/data` mount,
initially empty. More backend replicas would violate the single-process SQLite
contract; horizontal scaling needs a separate storage/concurrency design first.

No Google Drive mount, Google credential, personal archive, or host filesystem
is copied into an image or manifest. The application cannot reach external
services under its declared network policy. It starts as an empty local-data
application with athlete authentication still required behind Authelia MFA.

Ansible owns `fitness-tracker-runtime` and the namespace's TLS Secret. Run
`make fitness-credentials` to append stable application credentials to the
existing encrypted vault without rotating cluster credentials. Treat the vault
and its separate password as private recovery material. Argo CD references
these Secrets but never owns or publishes their contents.

The application project also forbids Secret resources, so a later manifest
cannot silently take over either Ansible-managed Secret.

The sibling app's publishing workflow tags images with the full source commit
SHA and emits `image-release.json` containing both pushed image digests. The
workload must pin those `@sha256:` references; `latest` and unreleased tags are
rejected by the production gate. Building or publishing a release requires
explicit approval, as do commits and pushes from this local working tree.

```bash
make fitness-check ALLOW_UNRELEASED=1
```

That command validates only a draft workload and does not deploy it. Future
temporary `release-required` image references are intentionally unusable.
After approved images are published, pin both digests, commit and publish the
reviewed homelab manifests, reconcile the external Secrets through Ansible,
then run:

```bash
make fitness-check
make fitness-deploy
```

The deployment helper refuses dirty application manifests, an unpublished local
revision, unreleased images, or missing runtime/TLS Secrets. It creates only the
Argo CD Application; Argo CD reconciles the workloads. Publication and an actual
Synced/Healthy result are separate from draft/template validation. The app is
not live merely because these source checks pass.

The live URL is `https://fitness.pn51.192.168.1.20.sslip.io`. The app retains
its own athlete session and CSRF protection after the outer Authelia login.
Retrieve credentials only through a trusted terminal/password-manager workflow,
never in chat. Back up SQLite through the application's consistent backup
command; an etcd snapshot does not contain its persistent application data.

### Verified Release

The deployed images were published by the successful fitness-tracker workflow
for source revision `e2af8408f0a1321d546fe014857dc6e4a0e4cb82`; both digest
manifests were also verified anonymously pullable before deployment. Argo CD
reconciles the published homelab source, and its Application is Synced/Healthy.
The backend and frontend are Ready with the retained state claim Bound.

A live test through the actual frontend verified athlete login, Secure/HttpOnly/
SameSite cookies, CSRF rejection, synthetic workout creation, readback after a
new backend pod, test-record deletion, and session revocation. Test credentials
were confined to process memory; no personal archive was read or imported and
no Google connection was attempted. The temporary test forward was closed.

To admit a different repository or namespace, review the project template and
the corresponding Ansible group variables; do not casually widen the project
to `*`. Do not edit Ansible-owned bootstrap resources through an Application.

Run `make argocd-chart-check`, `make configure`, `make verify`, and
`make idempotence` after changing the bootstrap. Chart upgrades can change CRDs;
Helm rollback does not restore application data or reverse CRD migrations.

See [security](security.md), [architecture](PN51/architecture-diagrams.md), and
[operations](operations.md).
