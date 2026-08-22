# homelab

My home Lab setup running K8S on `Asus PN51` minipc (K3S).

<!--
## For contributors

[Project tracking](https://thenewthinktank.atlassian.net/jira/software/projects/HOM/boards/3)
-->

## Local setup for documentation

```BASH
uv init
source .venv/bin/activate
uv add mkdocs-material
```

## Node provisioning

For repeatable Ubuntu node setup, the preferred path is the Ansible playbook in [pn51/ansible/playbook.yml](pn51/ansible/playbook.yml). The existing shell scripts in [pn51/ubuntu-node-bootstrap.sh](pn51/ubuntu-node-bootstrap.sh) and [pn51/ubuntu_hardening.sh](pn51/ubuntu_hardening.sh) are still useful for quick manual bootstrap, but Ansible is better for re-running changes across hosts.

## TODOs

- [ ] Host LLMs
- [ ] Host my own custom apps (fitness-tracker etc.)

- [x] Clean up docs/
- [x] Remove Raspberry pi
- [x] Replace FLUX CD with Argo CD
- [x] Add K8S manifest dirs and files
- [x] Add docs for monitoring setup
