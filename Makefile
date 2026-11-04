SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV ?= uv
TF := terraform -chdir=pn51/terraform
TF_VARS := -var-file=../../.local/terraform.tfvars.json
PYTHON := $(UV) run --frozen python
ANSIBLE := $(UV) run --frozen ansible-playbook
VAULT_FILE ?= .local/vault.yml
VAULT_ARGS ?= --vault-password-file .local/vault-password
CONFIG_FILE ?=
CONFIG_ARGS = $(if $(strip $(CONFIG_FILE)),--extra-vars '@$(CONFIG_FILE)')
REPLACEMENT_ARGS = $(if $(strip $(CONFIRM_REPLACEMENT)),--confirm '$(CONFIRM_REPLACEMENT)')

export PATH := $(CURDIR)/.venv/bin:$(CURDIR)/scripts:$(PATH)
export UV_CACHE_DIR := $(CURDIR)/.local/uv-cache
export UV_SYSTEM_CERTS := true
export SSL_CERT_FILE ?= /etc/ssl/cert.pem
export ANSIBLE_HOME := $(CURDIR)/.local/ansible
export ANSIBLE_LOCAL_TEMP := $(CURDIR)/.local/ansible/tmp
export HELM_CONFIG_HOME := $(CURDIR)/.local/helm/config
export HELM_CACHE_HOME := $(CURDIR)/.local/helm/cache
export HELM_DATA_HOME := $(CURDIR)/.local/helm/data
export TMPDIR := $(CURDIR)/.local/tmp
export CHECKPOINT_DISABLE := 1

.PHONY: help setup init plan apply inventory vault configure verify replace-worker destroy
.PHONY: lint test test-templates chart-check docs docs-serve check idempotence secrets-scan
.PHONY: kube-shell
.PHONY: workspace host init-local image trust-guest-keys tunnel
.PHONY: platform-check
.PHONY: argocd-chart-check
.PHONY: cutover

help:
	@printf '%s\n' \
	  'setup          Install locked Python tools and pinned Ansible collections' \
	  'host           Reconcile Ubuntu KVM host; enter sudo password in the terminal' \
	  'init-local     Prepare private Terraform inputs, encrypted credentials, and TLS' \
	  'image          Download and verify the pinned Ubuntu server cloud image' \
	  'init/plan/apply Manage four VMs; apply requires Terraform confirmation' \
	  'vault          Create encrypted credentials without plaintext files' \
	  'trust-guest-keys Verify guest SSH keys through the trusted libvirt connection' \
	  'tunnel         Forward the private K3s API to localhost:16443' \
	  'configure      Configure server guests, K3s, and monitoring from inventory' \
	  'kube-shell     Open a controller shell with only this lab kubeconfig selected' \
	  'verify         Check the live cluster, storage, Grafana, and Prometheus' \
	  'cutover        Guard, cold-back up old host K3s, then publish VM ingress' \
	  'idempotence    Apply twice and require an unchanged second run' \
	  'replace-worker NODE=pn51-worker-2  Guard, plan, and confirm a replacement' \
	  'check          Run offline infrastructure, template, chart, and documentation checks' \
	  'platform-check Render and validate MFA, TLS, restricted pods, and Headlamp RBAC' \
	  'secrets-scan   Scan Git history with redacted findings' \
	  'destroy        Terraform destroy; protected data disks deliberately block deletion'

workspace:
	@umask 077 && mkdir -p .local/tmp .local/ansible/tmp .local/helm/config .local/helm/cache .local/helm/data

setup: workspace
	$(UV) sync --frozen
	umask 077 && $(UV) run --frozen ansible-galaxy collection install --force -r pn51/ansible/requirements.yml -p .local/collections

host: workspace
	$(ANSIBLE) -i pn51/ansible/host-inventory.yml pn51/ansible/host.yml --ask-become-pass

cutover: workspace
	@test "$(CONFIRM)" = retire-host-k3s || { printf 'Set CONFIRM=retire-host-k3s after make verify passes.\n' >&2; exit 2; }
	$(ANSIBLE) -i pn51/ansible/host-inventory.yml pn51/ansible/cutover.yml --ask-become-pass --extra-vars retire_legacy_k3s=true

init-local: workspace
	$(PYTHON) scripts/homelab.py init-local

image: workspace
	$(PYTHON) scripts/homelab.py image

trust-guest-keys: inventory
	$(PYTHON) scripts/homelab.py trust-guest-keys

tunnel: inventory
	ssh -N -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=yes -o UpdateHostKeys=no -o ControlPath=none -L 127.0.0.1:16443:10.51.0.40:6443 pn51

init: workspace
	umask 077 && $(TF) init -input=false

plan: init image
	umask 077 && $(TF) plan $(TF_VARS)

apply: init image
	umask 077 && $(TF) apply $(TF_VARS)

inventory: workspace
	$(PYTHON) scripts/homelab.py inventory

vault: workspace
	$(PYTHON) scripts/homelab.py vault

configure: inventory
	$(ANSIBLE) pn51/ansible/playbook.yml --extra-vars '@$(VAULT_FILE)' $(CONFIG_ARGS) $(VAULT_ARGS)

kube-shell:
	@test -r .local/kubeconfig || { printf 'Run make configure to create the private kubeconfig first.\n' >&2; exit 1; }
	KUBECONFIG="$(CURDIR)/.local/kubeconfig" "$${SHELL:-/bin/bash}" -i

verify: workspace
	$(PYTHON) scripts/homelab.py verify

idempotence: configure
	umask 077 && ANSIBLE_STDOUT_CALLBACK=ansible.posix.json $(ANSIBLE) pn51/ansible/playbook.yml --extra-vars '@$(VAULT_FILE)' $(CONFIG_ARGS) $(VAULT_ARGS) > .local/idempotence.json
	$(PYTHON) scripts/homelab.py idempotence-check .local/idempotence.json

replace-worker: inventory
	@[[ -n "$(NODE)" ]] || { printf 'Set NODE to a generated worker name.\n' >&2; exit 2; }
	$(PYTHON) scripts/homelab.py replace-worker --node '$(NODE)' $(REPLACEMENT_ARGS)

destroy: init
	umask 077 && $(TF) destroy $(TF_VARS)

lint: workspace
	$(TF) fmt -check -recursive
	$(UV) run --frozen ruff check scripts tests
	$(UV) run --frozen ruff format --check scripts tests
	$(UV) run --frozen ansible-lint --offline pn51/ansible/playbook.yml pn51/ansible/host.yml pn51/ansible/cutover.yml tests/templates.yml

chart-check: workspace
	$(PYTHON) scripts/homelab.py chart-check

platform-check: test-templates
	$(PYTHON) scripts/homelab.py platform-check

argocd-chart-check: test-templates
	$(PYTHON) scripts/homelab.py argocd-chart-check

test-templates:
	$(ANSIBLE) -i pn51/ansible/inventory.example.yml tests/templates.yml

test: workspace
	$(TF) init -backend=false -input=false
	$(TF) validate
	$(TF) test
	$(MAKE) chart-check platform-check argocd-chart-check
	$(PYTHON) -m pytest

docs: workspace
	$(UV) run --frozen mkdocs build --strict

docs-serve:
	$(UV) run --frozen mkdocs serve --dev-addr 127.0.0.1:8000

secrets-scan:
	gitleaks git --redact --no-banner
	git ls-files --cached --others --exclude-standard -z | \
	  while IFS= read -r -d '' candidate; do \
	    if [[ -f "$$candidate" ]]; then cat -- "$$candidate"; printf '\n'; fi; \
	  done | gitleaks stdin --redact --no-banner

check: lint test docs
