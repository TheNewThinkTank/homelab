# Optional Application GitOps

The infrastructure bootstrap does not install Argo CD or deploy the existing
fitness-tracker example. Ansible owns the monitoring Helm release so that its
CRDs, secret boundary, and recovery path remain available without an application
GitOps controller.

If you later add Argo CD, keep its ownership separate from Terraform and the
Ansible-managed monitoring release. Do not let two reconcilers manage the same
objects. Review the example Application's automated sync/prune behavior, image
versions, namespace, service exposure, and application credentials before
applying it.

The existing application's Secret has empty values and is not a production
secret source. Use a dedicated encrypted-secret or external-secret workflow for
real applications; public Git must not contain populated plaintext Secret data.
Base64-encoding a Kubernetes Secret is not protection.

Public ingress, TLS, authentication, external DNS, application database backups,
and network policies are separate explicit additions. The base cluster disables
the default K3s ingress and service-load-balancer controllers and opens no
NodePort range.

See [security](security.md), [architecture](PN51/architecture-diagrams.md), and
[operations](operations.md).
