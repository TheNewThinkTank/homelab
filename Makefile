SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV ?= uv
TF := terraform -chdir=pn51/terraform
PYTHON := $(UV) run --frozen python
ANSIBLE := $(UV) run --frozen ansible-playbook
VAULT_FILE ?= .local/vault.yml
VAULT_ARGS ?= --ask-vault-pass
CONFIG_FILE ?=
CONFIG_ARGS = $(if $(strip $(CONFIG_FILE)),--extra-vars '@$(CONFIG_FILE)')

.PHONY: help setup init plan apply inventory vault configure verify replace-worker destroy
.PHONY: lint test test-templates chart-check docs docs-serve check idempotence secrets-scan
.PHONY: kube-shell

help:
	@printf '%s\n' \
	  'setup          Install locked Python tools and pinned Ansible collections' \
	  'init/plan/apply Manage four VMs; apply requires Terraform confirmation' \
	  'vault          Create encrypted credentials without plaintext files' \
	  'configure      Configure Desktop, K3s, and monitoring from generated inventory' \
	  'kube-shell     Open a controller shell with only this lab kubeconfig selected' \
	  'verify         Check the live cluster, storage, Grafana, and Prometheus' \
	  'idempotence    Apply twice and require an unchanged second run' \
	  'replace-worker NODE=pn51-worker-2  Guard, plan, and confirm a replacement' \
	  'check          Run offline infrastructure, template, chart, and documentation checks' \
	  'secrets-scan   Scan Git history with redacted findings' \
	  'destroy        Destroy VMs and their disks; requires Terraform confirmation'

setup:
	$(UV) sync --frozen
	umask 077 && $(UV) run --frozen ansible-galaxy collection install --force -r pn51/ansible/requirements.yml -p .local/collections

init:
	umask 077 && $(TF) init -input=false

plan: init
	umask 077 && $(TF) plan

apply: init
	umask 077 && $(TF) apply

inventory:
	$(PYTHON) scripts/homelab.py inventory

vault:
	$(PYTHON) scripts/homelab.py vault

configure: inventory
	$(ANSIBLE) pn51/ansible/playbook.yml --extra-vars '@$(VAULT_FILE)' $(CONFIG_ARGS) $(VAULT_ARGS)

kube-shell:
	@test -r .local/kubeconfig || { printf 'Run make configure to create the private kubeconfig first.\n' >&2; exit 1; }
	KUBECONFIG="$(CURDIR)/.local/kubeconfig" "$${SHELL:-/bin/bash}" -i

verify:
	$(PYTHON) scripts/homelab.py verify

idempotence: configure
	umask 077 && ANSIBLE_STDOUT_CALLBACK=ansible.posix.json $(ANSIBLE) pn51/ansible/playbook.yml --extra-vars '@$(VAULT_FILE)' $(CONFIG_ARGS) $(VAULT_ARGS) > .local/idempotence.json
	$(PYTHON) scripts/homelab.py idempotence-check .local/idempotence.json

replace-worker: inventory
	@[[ -n "$(NODE)" ]] || { printf 'Set NODE to a generated worker name.\n' >&2; exit 2; }
	$(PYTHON) scripts/homelab.py replace-worker --node '$(NODE)'

destroy: init
	umask 077 && $(TF) destroy

lint:
	$(TF) fmt -check -recursive
	$(UV) run --frozen ruff check scripts tests
	$(UV) run --frozen ruff format --check scripts tests
	$(UV) run --frozen ansible-lint --offline pn51/ansible/playbook.yml tests/templates.yml

chart-check:
	$(PYTHON) scripts/homelab.py chart-check

test-templates:
	$(ANSIBLE) -i pn51/ansible/inventory.example.yml tests/templates.yml

test:
	$(TF) init -backend=false -input=false
	$(TF) validate
	$(TF) test
	$(MAKE) chart-check test-templates
	$(PYTHON) -m pytest

docs:
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
