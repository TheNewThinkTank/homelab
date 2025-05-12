# Linux Hardening for Asus PN51 Mini PC

Based on my setup (Asus PN51 running Ubuntu via Ventoy for hobby projects including self-hosted K8S), implementing some security hardening measures is beneficial, since I will be hosting web applications that may be accessible from the internet.

My activities listed below increase my attack surface, making security hardening important.
- Self-hosting web applications
- Running a Kubernetes cluster (RKE)
- Using ArgoCD for deployments
- Maintaining public GitHub repositories

## Recommended Approach

Rather than using a single "do-it-all" hardening script (which might be too aggressive or not tailored to my specific needs), I choose a more measured approach:

### 1. Starting with a Baseline Hardening Tool

I currently consider using one of these established tools:

- **Lynis** - An open-source security auditing tool that can both assess my system and provide hardening recommendations
- **OpenSCAP** - Security compliance and hardening framework
- **Ubuntu's built-in security features** - AppArmor, UFW (Uncomplicated Firewall), etc.

### 2. Key Areas to Focus On

For my specific setup (home K8S cluster with web apps), I prioritize:

- **Network security**: Configure UFW to limit exposed ports
- **SSH hardening**: Key-based authentication, disable root login
- **Container security**: Implement pod security policies in K8S
- **Regular updates**: Keeping my system and applications updated
- **Secure CI/CD practices**: For my ArgoCD workflows
- **Least privilege principle**: For all services and applications

### 3. K8S-Specific Security

Since I am running RKE, I also plan to:
- Implement network policies
- Use RBAC properly
- Consider tools like Falco for runtime security monitoring
