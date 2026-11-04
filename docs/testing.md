# Testing and Acceptance

There are two different claims to verify: the source describes a coherent lab,
and that lab actually converges on your PN51. CI proves the first. Only live
acceptance and recovery exercises can prove the second.

## Credential-Free Gates

```bash
make setup
make check
```

For future unreleased fitness workloads using deliberate `release-required`
image markers, use `make check ALLOW_UNRELEASED=1` for draft validation. This does not
relax `make fitness-deploy`: its production check always requires published
digest-pinned images. After a release is pinned, ordinary `make check` is the
required gate.

The chart download and dependency installation require internet access, but no
host, guest SSH, vault, or Kubernetes credentials. Tests never call Terraform apply
against the host.

| Gate | Evidence |
| --- | --- |
| Terraform fmt/validate | Configuration matches the pinned real provider schema |
| Terraform mocked plans | Exactly four VMs; one server/three workers; RAM budget; NAT; cloud-init; separate retained disks; deterministic inventory |
| Negative Terraform cases | Small/excessive RAM, gateway/IP collisions, overlapping networks, private-key input, bad image digest rejected |
| Ansible production lint | Fully qualified modules, schema/syntax, task conventions, YAML formatting |
| Real Ansible templates | All four host configs rendered; server/agent flag separation; token-file use; unchanged second render |
| Platform render gate | 33 real resources; seven MFA/TLS routes, restricted containers, credential-free Homepage, network policies, read-only Headlamp RBAC |
| Argo CD chart gate | Exact official archive checksum, three CRDs, private services, non-root workloads, disabled anonymous access, repository/namespace project limits |
| Fitness workload gate | Ten local-data resources; one SQLite writer, Recreate rollout, retained state, read-only imports, MFA/TLS, private services, narrow egress, and release image pins |
| Python regressions | Private modes, symlinks, vault encryption/failure, inventory precedence, replacement scope and PV guards, idempotence evidence |
| Dotfiles role contracts | Mutable revisions rejected before package installation; public source and ubuntu ownership; local configuration fixture changes only when necessary |
| Real pinned chart | Exact archive checksum; strict Helm lint; render against pinned Kubernetes version; private services; persistent storage; existing Grafana Secret |
| CRD regression | All ten real CRDs parse safely; YAML `=` scalar handled without Python-object construction |
| MkDocs strict | Navigation and local documentation links build without warnings |
| Secret scanning | Redacted Git-history scan in CI; tracked and nonignored working files scanned before publication |

The GitHub workflow pins its actions to commit IDs, uses a frozen Python lockfile,
and grants infrastructure validation read-only repository access. It has no
homelab credentials or self-hosted runner. Documentation publishing has its own
separate write-capable workflow.

## How to Run Live Acceptance

After [initial configuration](provisioning.md):

```bash
make verify
```

This requires the private inventory/kubeconfig and a reachable cluster. It checks
all declared node names, exact K3s versions and Ready conditions, monitoring
Deployment/StatefulSet/DaemonSet replica health, retained Bound application claims,
Grafana database health, healthy Prometheus targets, Authelia/Headlamp/Homepage,
Argo CD workload and server health, live project restrictions, DNS, Traefik,
metrics, local-path storage, and `helm test`.
Helm test creates a temporary chart test pod; it does not rebuild VMs.

Also verify host and VM boot behavior, guest input firewall rules, and that a
non-admin machine cannot reach guest SSH or the server API. After cutover, test
HTTPS certificate validation, Authelia MFA, and denied anonymous dashboard
access. An internal health check does not prove the external access boundary.

## How to Prove Full Convergence

```bash
make idempotence
```

The first run establishes desired state. The second full run writes a private
JSON callback report and must show **zero changes, failures, unreachable hosts,
rescued tasks, and ignored failures** on the exact four expected hosts. An empty
report, missing host, or partial `--limit` run cannot pass the evidence checker.

The report stays under ignored `.local/`; do not upload it as a public artifact.
When dotfiles is enabled, run `make idempotence CONFIG_FILE=.local/config.yml`.
The role checks package state, missing plugins, and managed configuration
separately; it does not hide a full bootstrap behind an always-unchanged command.
If a task changes again, inspect that exact task rather than hiding it with a
blanket `changed_when: false`. Pure observation commands are intentionally
unchanged; actual package, Secret, file, service, and Helm changes are not hidden.

## How to Exercise Recovery

On an isolated test copy, prove that a stateless worker can be replaced and
rejoin under its original name, that protected data survives root replacement,
that unprotected local data is refused, and that
etcd plus application data can be restored from off-host backups. Run live
acceptance and idempotence after each exercise. Never test a production restore
against conflicting libvirt names or addresses.

## Verification Limits

An application is not deployed merely because draft checks pass.
Release verification additionally needs approved image builds, published image
digests and Git manifests, external runtime/TLS Secrets, an Argo CD
Synced/Healthy Application, and actual readiness/login/write/persistence checks.
Local API/config/SQLite tests use isolated fixtures with dotenv disabled; they
do not establish container or cluster behavior and do not call Google services.

For the released fitness app, the CI container/browser gates and live
Synced/Healthy, readiness, login/CSRF, synthetic write, retained-state restart,
and cleanup checks have passed. This does not establish a full disaster restore
or import of personal training data; no Google integration was exercised.

Mocked plans do not prove libvirt permissions, image boot behavior, guest-agent
startup, protected filesystem mounting, CNI traffic, kernel compatibility, or
physical capacity. Chart rendering does not prove successful operator scheduling
or database migration. Local template convergence is not a substitute for the
full live second-run check.

The repository deliberately does not claim those live results until you run the
gates on your host. Known controller collection deprecation warnings are not
suppressed globally; review them when updating pinned dependencies.

The sibling dotfiles project has independent offline and real-plugin tests for
MacBook personal/work profiles. Its Ubuntu 26.04 CI covers both the workstation
and lightweight homelab package sets. With Docker running, use
`DOTFILES_PACKAGE_SET=homelab make ubuntu` there to test the lightweight native
installer. A passing local Ansible fixture does not prove the full VM deployment
or replace those native Linux checks.

## Troubleshooting

Run the failing slice directly with `make lint`, `make chart-check`,
`make test-templates`, or `uv run --frozen python -m pytest`. Use
`terraform -chdir=pn51/terraform test` for mocked plans. For a live failure,
inspect node/pod events and the exact failing Ansible task without enabling
secret-bearing debug output.

See [operations](operations.md), [reference](reference.md), and
[monitoring troubleshooting](observability.md).