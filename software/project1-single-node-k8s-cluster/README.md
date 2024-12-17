# Project 1

Single-node Kubernetes cluster to test GitOps workflows,
for learning and experimentation.

## Why a Single-Node Cluster Works

**Resource Availability**:
8GB of RAM is enough to run Kubernetes components (control plane and worker node) and lightweight workloads.

**Learning Focus**:
For testing GitOps workflows, the key is deploying and managing applications with tools like ArgoCD or FluxCD, which doesn't require multiple nodes.

**Expandability**:
You can add more Raspberry Pis later for a multi-node setup.

## Steps to Set Up a Single-Node Kubernetes Cluster

1. Install Kubernetes

- Use a lightweight distribution like k3s or microk8s for better performance on a single node:
- - k3s: A lightweight Kubernetes distribution, easy to set up and resource-efficient.
- - microk8s: Another lightweight option maintained by Canonical.
- Follow installation instructions for your chosen distribution.

2. Install GitOps Tool

- Deploy ArgoCD or FluxCD to manage GitOps workflows. Both tools are lightweight and well-suited for testing on a single node.
- Example: Install ArgoCD using its Helm chart or YAML manifest.

3. Configure Your GitOps Workflow

- Set up a GitHub repo to hold your Kubernetes manifests or Helm charts.
- Configure ArgoCD/FluxCD to sync with the repo.

4. Test Deployments

- Deploy lightweight apps, such as:
- - Nginx or Apache server
- - A simple web app (e.g., Flask or React)
- - Monitoring tools (e.g., Prometheus and Grafana)

5. Monitor Resources

- Install a monitoring tool like k9s or Lens to track the resource usage of your single-node cluster.

## What to Keep in Mind

- Resource Constraints: With only 8GB RAM, avoid deploying resource-heavy apps (e.g., databases like PostgreSQL) alongside the control plane.
- Scaling Later: If you add more Raspberry Pis, you can transition to a multi-node setup by joining them to the existing cluster.
- Storage: Use an external SSD for better performance if you plan to deploy applications that require persistent storage.

## TODO: add step-by-step guidance on setting up k3s or ArgoCD
