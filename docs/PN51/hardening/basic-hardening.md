# Basic Linux Hardening Script for Ubuntu

My basic [hardening script](../../../pn51/ubuntu_hardening.sh) for my Ubuntu system running on the Asus PN51. This script `ubuntu_hardening.sh` covers essential security measures without being overly aggressive, making it suitable for my home K8S setup.

## Important Notes Before Running This Script:

1. **Review the script carefully** before running it to ensure it aligns with your specific needs.

2. **SSH Warning**: The script disables password authentication for SSH and requires key-based authentication.
Make sure you have SSH keys set up before running this script, or you might lock yourself out.

3. **Firewall Configuration**: The script includes common K8S ports, but you may need to adjust these based on your specific RKE setup.

4. **Backup**: Always create a system backup before applying security hardening measures.

5. **Testing**: Consider testing this script in a non-production environment first.

## How to Use the Script:

1. Save the script to a file named `ubuntu_hardening.sh`
2. Make it executable: `chmod +x ubuntu_hardening.sh`
3. Run it with sudo: `sudo ./ubuntu_hardening.sh`
4. Reboot your system after completion

## Additional K8S-Specific Security

For my K8S environment, I am considering these additional measures (not included in the script):

1. Use `kube-bench` to check my cluster against CIS K8S Benchmarks
2. Implement network policies to restrict pod-to-pod communication
3. Use RBAC properly to limit access to the K8S API
4. Implementing a service mesh like Istio for additional security controls
5. Use secrets management solutions rather than storing secrets in plain text
