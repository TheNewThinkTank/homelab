# Architecture Diagrams

## Automating Asus PN51 Setup - C4 Model Diagrams

This document provides two diagrams using the C4 model to visualize the architecture for automating the setup of an Asus PN51 using GitHub Actions and ArgoCD.

---

## Context Diagram

The Context Diagram provides a high-level overview of the external systems interacting with the automation setup.

```mermaid
C4Context
    title Context Diagram for Automating Asus PN51 Setup

    Person(user, "Developer", "Manages the homelab repository and triggers workflows.")
    System(github, "GitHub", "Hosts the `homelab` repository and runs GitHub Actions workflows.")
    System(pn51, "Asus PN51", "The target machine to be configured and managed.")
    System(argocd, "ArgoCD", "Monitors the Git repository and applies configurations automatically.")

    Rel(user, github, "Pushes code to")
    Rel(github, pn51, "Triggers Terraform/Ansible via SSH")
    Rel(argocd, pn51, "Applies configurations from Git")
    Rel(user, argocd, "Configures ArgoCD applications")
```

```mermaid
C4Container
    title Container Diagram for Automating Asus PN51 Setup

    Person(user, "Developer", "Manages the homelab repository and triggers workflows.")
    System_Boundary(github_system, "GitHub") {
        Container(github_repo, "Repository", "Git", "Stores Terraform and Ansible configurations.")
        Container(github_actions, "GitHub Actions", "CI/CD", "Runs workflows to apply Terraform and Ansible configurations.")
    }
    System_Boundary(pn51_system, "Asus PN51") {
        Container(ssh_server, "SSH Server", "OpenSSH", "Allows remote access to the PN51.")
        Container(terraform_target, "Terraform Target", "Infrastructure", "Managed by Terraform configurations.")
        Container(ansible_target, "Ansible Target", "Configuration", "Managed by Ansible playbooks.")
    }
    System_Boundary(argocd_system, "ArgoCD") {
        Container(argocd_app, "ArgoCD Application", "GitOps", "Monitors the Git repository and applies changes.")
    }

    Rel(user, github_repo, "Pushes code to")
    Rel(github_repo, github_actions, "Triggers workflows")
    Rel(github_actions, ssh_server, "Runs Terraform/Ansible via SSH")
    Rel(ssh_server, terraform_target, "Applies infrastructure changes")
    Rel(ssh_server, ansible_target, "Applies configuration changes")
    Rel(argocd_app, ssh_server, "Applies configurations from Git")
    Rel(user, argocd_app, "Configures ArgoCD applications")
```
