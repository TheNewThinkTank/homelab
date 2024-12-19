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

Use a lightweight distribution like k3s for better performance on a single node.
Easy to set up and resource-efficient.

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

## Step-by-step guidance on setting up k3s and FluxCD

Setting up K3s on the Raspberry Pi 5 (z-pi) using GitOps to ensure a repeatable, automated, and secure setup process.
Below is a step-by-step guide for this installation, ensuring sensitive data is not exposed in this public GitHub repository.

---

### **1. Prerequisites**
1. **Hardware**:
   - Raspberry Pi 5 with Raspbian or Ubuntu installed.
   - Internet access.

2. **Software**:
   - `git`, `kubectl`, and `helm` installed on your workstation.
   - Access to your public GitHub repo, `homelab`.

3. **Secure Files**:
   - Use a private `.secrets/` directory (ignored by `.gitignore`) for sensitive data.
   - Store secrets in a vault like HashiCorp Vault or use sealed-secrets for GitOps.

---

### **2. Prepare the Raspberry Pi**
1. **Install Necessary Tools**:
   ```bash
   sudo apt update && sudo apt upgrade -y
   curl -sfL https://get.k3s.io | sh -
   ```

2. **Verify Installation**:
   ```bash
   sudo k3s kubectl get nodes
   ```

3. **Set Up GitOps Directory**:
   Create a directory for `GitOps` configuration:
   ```bash
   mkdir -p ~/gitops && cd ~/gitops
   git clone https://github.com/<your-username>/homelab.git
   ```

---

### **3. Configure GitHub Repo**
1. **Set up `.gitignore`**:
   Ensure the `.gitignore` file in your `homelab` repo excludes sensitive data:
   ```bash
   .secrets/
   kubeconfig.yaml
   private-keys/
   ```

2. **Install Flux for GitOps**:
   Use Flux to sync your Raspberry Pi with your GitHub repository:
   ```bash
   curl -s https://fluxcd.io/install.sh | sudo bash
   flux check --pre
   ```

3. **Bootstrap Flux**:

   ```bash
   flux bootstrap github \
     --owner=TheNewThinkTank \
     --repository=homelab \
     --branch=main \
     --path=clusters/z-pi \
     --personal
   ```

   This will configure Flux to monitor the `clusters/z-pi` directory in your repo.

---

### **4. Add Applications**
1. **Helm Releases**:
   In the `clusters/z-pi/` directory, define Helm releases for applications like `nginx`:
   ```yaml
   apiVersion: helm.toolkit.fluxcd.io/v2beta1
   kind: HelmRelease
   metadata:
     name: nginx
     namespace: default
   spec:
     chart:
       spec:
         chart: nginx
         version: 1.2.3
         sourceRef:
           kind: HelmRepository
           name: bitnami
           namespace: flux-system
   ```

2. **Kubernetes Manifests**:
   Add manifests for essential services:
   - **Ingress Controller**
   - **Service Monitor**
   - **Storage Class** (for `local-path`).

---

### **5. Secure Secrets**
1. **Use Sealed Secrets**:
   Install the Sealed Secrets controller on the cluster:
   ```bash
   kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.20.0/controller.yaml
   ```

2. **Encrypt Secrets**:
   Encrypt secrets before committing them to your GitHub repo:
   ```bash
   kubeseal --scope namespace-wide \
     --controller-name=sealed-secrets \
     --controller-namespace=flux-system \
     -o yaml < your-secret.yaml > sealed-secret.yaml
   ```

3. **Use `.gitignore`**:
   Add raw secret files to `.gitignore` and only commit the sealed versions.

---

### **6. Update GitHub Repo**
Push the changes to your repository:
```bash
git add .
git commit -m "Initial GitOps setup for z-pi"
git push origin main
```

---

### **7. Monitor and Manage**
1. **Flux Reconciliation**:
   Verify that Flux is pulling changes:
   ```bash
   flux get all --namespace flux-system
   ```

2. **Check Cluster Health**:
   Use `kubectl` to monitor the state of the cluster:
   ```bash
   kubectl get pods --all-namespaces
   ```

---

### **Best Practices for Security**
1. **Use Firewalls**:
   Configure `ufw` or equivalent to block unauthorized access.
   ```bash
   sudo ufw enable
   sudo ufw allow ssh
   sudo ufw allow 6443
   ```

2. **SSH Key Management**:
   Use SSH keys for access instead of passwords.

3. **Monitor Logs**:
   Enable monitoring tools like Prometheus and Grafana.

4. **Limit Resource Exposure**:
   Avoid exposing the K3s API server directly to the internet.
