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

The sibling app publishes both images only after Python, frontend, container,
browser, and image vulnerability gates pass. Its ordered release tag is
`main-<workflow run number>.<run attempt>`; a rerun gets a distinct tag rather
than overwriting an earlier release. The OCI revision label and
`image-release.json` preserve the full source commit SHA. The artifact contains
the release tag and both `:main-<run>.<attempt>@sha256:` references.

Source provenance comes from that immutable image's OCI label and release
artifact, not a fixed Deployment annotation that Renovate would leave stale.

The workload keeps digest pins, so a registry tag cannot silently change running
code. Both tagged references must name the same release; mixed releases,
`latest`, and unreleased tags are rejected by the production gate. Existing
bare digest pairs remain valid for recovery only while the fitness Renovate
rule is disabled. Enabling the rule requires a numbered tag on both initial
pins; an untagged digest would make Docker discovery fall back to `latest`.
The source regression guard enforces this bootstrap requirement. Initial local
publication still requires approval; ongoing updates use the automation below.

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

### Automated Image Promotion

The hosted Renovate GitHub App needs access only to
`TheNewThinkTank/homelab`. It discovers the two public GHCR repositories; no
GitHub token or Renovate workload is installed on PN51. The repository's
`renovate.json` enables only the Kubernetes manager and only
`pn51/dev/fitness-tracker-k8s/deployment.yaml`. Terraform, Ansible, Helm,
controller dependencies, and unrelated images are not auto-upgraded.

Renovate groups backend and frontend into one `fitness-tracker release` PR,
requires at least two updates, and pins both selected digests. Its numeric
versioning ignores commit-SHA, `latest`, branch, and development tags. An
incomplete publication cannot bypass the matching-release validation in CI.
GitHub must allow squash merging and auto-merge; protect `main` with both
`validate` and `secrets` required checks before enabling native auto-merge.
GitHub branch protection enforces those checks for native auto-merge; current
Renovate versions no longer support the old `requiredStatusChecks` setting.
The required check producer is GitHub Actions, the branch must be up to date,
and administrators cannot bypass the checks. Force pushes and deletion are disabled.
Do not remove these protections or allow another CI job to reuse their names.

The delivery path is:

1. Merge reviewed application code to fitness-tracker `main`.
2. Successful release CI publishes a paired, uniquely tagged image release.
3. Renovate discovers it on its hosted scan and opens a grouped homelab PR.
4. Both homelab CI checks pass before GitHub squash-merges the image changes.
5. Argo CD's existing automated sync, self-heal, and prune reconcile Git to K3s.

Discovery and Argo polling are asynchronous, not a synchronous deploy hook.
`prConcurrentLimit: 1` avoids competing fitness release PRs. Do not add an Argo
image updater or a direct `kubectl set image` job: Git remains the only
application desired-state source. The backend's `Recreate` rollout has a brief
unavailable interval; the retained SQLite claim is not replaced by an image
update. A grouped PR is not an atomic two-Deployment rollout.

After a merged release, verify the Application and image references rather than
assuming a merged PR means a healthy deployment:

```bash
kubectl --kubeconfig .local/kubeconfig -n argocd get application fitness-tracker-argo-application
kubectl --kubeconfig .local/kubeconfig -n fitness-tracker get deployment,pod,pvc
kubectl --kubeconfig .local/kubeconfig -n fitness-tracker get deployment -o 'custom-columns=NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image'
```

For troubleshooting, inspect the Renovate Dependency Dashboard and grouped PR
checks first, then the Application's sync/health and Pod events. A failed image
scan means no qualified release; a partial image publication or mismatched PR
must wait for a complete pair, never bypass validation.

To pause delivery, set `enabled: false` on the fitness package rule and merge
that change before reverting both image references together to a known-good
pair. Argo CD will reconcile the Git rollback. Re-enabling the rule resumes
promotion, including releases newer than the rollback. Container rollback does
not reverse a SQLite schema migration: take a consistent backup and disable
auto-merge before releases that need a separate data migration or restore.
Keep the PVC and Ansible-owned Secrets intact.

### Initial Release Qualification

The initial deployed images were published by the successful fitness-tracker workflow
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
