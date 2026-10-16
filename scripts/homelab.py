from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from ipaddress import IPv4Address
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.constructor import SafeConstructor
from ruamel.yaml.error import YAMLError

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
TERRAFORM = ["terraform", f"-chdir={ROOT / 'pn51/terraform'}"]


def execute(command: list[str], *, capture: bool = False, stdin: str | None = None) -> str:
    result = subprocess.run(
        command,
        check=True,
        text=True,
        input=stdin,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout or ""


class KubernetesSafeConstructor(SafeConstructor):
    yaml_constructors = SafeConstructor.yaml_constructors | {
        "tag:yaml.org,2002:value": SafeConstructor.construct_yaml_str,
    }


def parse_yaml_documents(content: str) -> list[dict[str, Any]]:
    parser = YAML(typ="safe", pure=True)
    parser.version = (1, 2)
    parser.Constructor = KubernetesSafeConstructor
    documents = [document for document in parser.load_all(content) if document]
    if any(not isinstance(document, dict) for document in documents):
        raise ValueError("Expected YAML object documents.")
    return documents


def chart_crds(chart: str, version: str | None = None) -> list[dict[str, Any]]:
    command = ["helm", "show", "crds", chart]
    if version:
        command.extend(["--version", version])
    documents = parse_yaml_documents(execute(command, capture=True))
    if not documents or any(item.get("kind") != "CustomResourceDefinition" for item in documents):
        raise ValueError("The chart must provide Kubernetes CRDs, not arbitrary resources.")
    return documents


def private_write(target: Path, content: str, *, overwrite: bool = True) -> None:
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError("Refusing to write private data through a symlink.")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.parent.chmod(0o700)
    if not overwrite:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def validate_inventory(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    try:
        root = inventory["all"]
        cluster_name = root["vars"]["cluster_name"]
        groups = root["children"]["k3s_cluster"]["children"]
        servers = groups["k3s_server"]["hosts"]
        agents = groups["k3s_agents"]["hosts"]
        if root["vars"]["ansible_user"] != "ubuntu":
            raise ValueError("The generated inventory must use the ubuntu guest account.")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,30}[a-z0-9]", cluster_name):
            raise ValueError("Invalid cluster name.")
        if set(servers) != {f"{cluster_name}-server-1"} or set(agents) != {
            f"{cluster_name}-worker-{index}" for index in range(1, 4)
        }:
            raise ValueError(
                "Expected exactly one server and three deterministically named workers."
            )
        hosts = servers | agents
        addresses = [str(IPv4Address(host["ansible_host"])) for host in hosts.values()]
        identifiers = [host["proxmox_vm_id"] for host in hosts.values()]
        if len(set(addresses)) != 4 or len(set(identifiers)) != 4:
            raise ValueError("VM addresses and IDs must be unique.")
        if any(type(identifier) is not int or identifier < 100 for identifier in identifiers):
            raise ValueError("Invalid Proxmox VM ID.")
        return hosts
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Invalid generated Ansible inventory structure.") from error


def generate_inventory() -> None:
    inventory = json.loads(
        execute([*TERRAFORM, "output", "-json", "ansible_inventory"], capture=True)
    )
    validate_inventory(inventory)
    private_write(LOCAL / "inventory.json", json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    print("Generated private .local/inventory.json for four guests.")


def create_vault(target: Path) -> None:
    if target.exists() or target.is_symlink():
        raise ValueError(
            "The vault already exists; use ansible-vault edit instead of regenerating it."
        )
    plaintext = json.dumps(
        {"k3s_token": secrets.token_hex(32), "grafana_admin_password": secrets.token_urlsafe(32)}
    )
    ciphertext = execute(
        ["ansible-vault", "encrypt", "--output", "-"], capture=True, stdin=plaintext
    )
    if not ciphertext.startswith("$ANSIBLE_VAULT;"):
        raise ValueError("Vault encryption did not produce an Ansible Vault document.")
    private_write(target, ciphertext, overwrite=False)
    print("Created encrypted .local/vault.yml; plaintext credentials were never written to disk.")


def validate_idempotence(report: dict[str, Any], expected_hosts: set[str] | None = None) -> None:
    statistics = report.get("stats", {})
    if not statistics or (expected_hosts is not None and set(statistics) != expected_hosts):
        raise ValueError("Idempotence evidence must include every expected cluster host.")
    for hostname, counts in statistics.items():
        if any(
            counts.get(field, 0) != 0
            for field in ("changed", "failures", "unreachable", "rescued", "ignored")
        ):
            raise ValueError(f"The second run was not clean and unchanged on {hostname}.")


def load_settings() -> dict[str, Any]:
    source = ROOT / "pn51/ansible/group_vars/all.yml"
    return parse_yaml_documents(source.read_text(encoding="utf-8"))[0]


def validate_monitoring(documents: list[dict[str, Any]]) -> None:
    services = [item for item in documents if item.get("kind") == "Service"]
    if not services or any(
        item["spec"].get("type", "ClusterIP") != "ClusterIP" for item in services
    ):
        raise ValueError("Monitoring services must remain private ClusterIP services.")
    if any(item.get("kind") == "Ingress" for item in documents):
        raise ValueError("Monitoring must not create a public ingress by default.")
    for item in documents:
        if item.get("kind") == "Secret" and "admin-password" in item.get("data", {}):
            raise ValueError("Grafana credentials must not be stored in the Helm release.")
    exporters = [
        item
        for item in documents
        if item.get("kind") == "DaemonSet" and "node-exporter" in item["metadata"]["name"]
    ]
    if len(exporters) != 1:
        raise ValueError("Expected exactly one node-exporter DaemonSet.")
    exporter = exporters[0]["spec"]["template"]["spec"]
    if exporter.get("hostNetwork", False) or any(
        port.get("hostPort", 0) != 0
        for container in exporter["containers"]
        for port in container.get("ports", [])
    ):
        raise ValueError("Node-exporter must not expose a host-network metrics port.")
    prometheus = [item for item in documents if item.get("kind") == "Prometheus"]
    alertmanager = [item for item in documents if item.get("kind") == "Alertmanager"]
    claims = [item for item in documents if item.get("kind") == "PersistentVolumeClaim"]
    if not (prometheus and alertmanager and claims):
        raise ValueError("Expected Prometheus, Alertmanager, and persistent Grafana storage.")
    if "volumeClaimTemplate" not in prometheus[0]["spec"].get("storage", {}):
        raise ValueError("Prometheus must use persistent storage.")
    if "volumeClaimTemplate" not in alertmanager[0]["spec"].get("storage", {}):
        raise ValueError("Alertmanager must use persistent storage.")
    grafana = [
        item
        for item in documents
        if item.get("kind") == "Deployment" and item["metadata"]["name"].endswith("grafana")
    ]
    references = [
        value.get("valueFrom", {}).get("secretKeyRef", {})
        for deployment in grafana
        for container in deployment["spec"]["template"]["spec"]["containers"]
        for value in container.get("env", [])
    ]
    if {"name": "grafana-admin", "key": "admin-password"} not in references:
        raise ValueError("Grafana must reference the separately managed administrator Secret.")


def check_chart() -> None:
    settings = load_settings()
    version = settings["monitoring_chart_version"]
    archive = LOCAL / f"kube-prometheus-stack-{version}.tgz"
    LOCAL.mkdir(mode=0o700, exist_ok=True)
    if not archive.exists():
        execute(
            [
                "helm",
                "pull",
                "kube-prometheus-stack",
                "--repo",
                "https://prometheus-community.github.io/helm-charts",
                "--version",
                version,
                "--destination",
                str(LOCAL),
            ]
        )
    expected = settings["monitoring_chart_checksum"].removeprefix("sha256:")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise ValueError(
            "Cached chart checksum mismatch; inspect and remove the archive before retrying."
        )
    kubernetes_version = settings["k3s_version"].removeprefix("v").split("+")[0]
    values = ROOT / "pn51/monitoring/values.yml"
    execute(
        [
            "helm",
            "lint",
            str(archive),
            "--strict",
            "--kube-version",
            kubernetes_version,
            "--values",
            str(values),
        ]
    )
    rendered = execute(
        [
            "helm",
            "template",
            settings["monitoring_release_name"],
            str(archive),
            "--namespace",
            settings["monitoring_namespace"],
            "--kube-version",
            kubernetes_version,
            "--values",
            str(values),
            "--include-crds",
        ],
        capture=True,
    )
    documents = parse_yaml_documents(rendered)
    validate_monitoring(documents)
    crds = chart_crds(str(archive))
    if len(crds) != 10:
        raise ValueError("The pinned chart's CRD inventory changed; review the upgrade explicitly.")
    print(f"Validated {len(documents)} rendered resources, 10 CRDs, and the pinned chart checksum.")


def local_volumes_for_node(volumes: list[dict[str, Any]], node: str) -> list[str]:
    blockers = []
    for volume in volumes:
        specification = volume.get("spec", {})
        terms = (
            specification.get("nodeAffinity", {}).get("required", {}).get("nodeSelectorTerms", [])
        )
        selectors = [
            expression
            for term in terms
            for expression in term.get("matchExpressions", []) + term.get("matchFields", [])
            if expression.get("key") in {"kubernetes.io/hostname", "metadata.name"}
        ]
        attached = any(
            (selector.get("operator") == "In" and node in selector.get("values", []))
            or (selector.get("operator") == "NotIn" and node not in selector.get("values", []))
            for selector in selectors
        )
        uncertain_local = (
            "hostPath" in specification or "local" in specification
        ) and not selectors
        if attached or uncertain_local:
            blockers.append(volume["metadata"]["name"])
    return blockers


def validate_replacement_plan(plan: dict[str, Any], node: str) -> None:
    suffix = f"[{json.dumps(node)}]"
    target = "proxmox_virtual_environment_vm.node" + suffix
    allowed = {
        target,
        "proxmox_virtual_environment_firewall_rules.node" + suffix,
        "proxmox_virtual_environment_firewall_options.node" + suffix,
    }
    replacement = False
    for resource in plan.get("resource_changes", []):
        actions = resource["change"]["actions"]
        if actions in (["no-op"], ["read"]):
            continue
        if resource["address"] not in allowed:
            raise ValueError(
                "Replacement plan changes resources outside the selected worker; aborting."
            )
        if resource["address"] == target:
            replacement = sorted(actions) == ["create", "delete"]
    if not replacement:
        raise ValueError("Expected an explicit replacement of exactly the selected worker VM.")


def node_ready(node: dict[str, Any]) -> bool:
    return any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in node.get("status", {}).get("conditions", [])
    )


def replace_worker(node: str) -> None:
    inventory = json.loads((LOCAL / "inventory.json").read_text(encoding="utf-8"))
    hosts = validate_inventory(inventory)
    groups = inventory["all"]["children"]["k3s_cluster"]["children"]
    if node not in groups["k3s_agents"]["hosts"]:
        raise ValueError(
            "Only a generated worker name may be replaced; "
            "control-plane replacement needs a restore."
        )
    kubectl = ["kubectl", "--kubeconfig", str(LOCAL / "kubeconfig")]
    nodes = json.loads(execute([*kubectl, "get", "nodes", "-o", "json"], capture=True))["items"]
    healthy = {item["metadata"]["name"] for item in nodes if node_ready(item)}
    if not (set(hosts) - {node}).issubset(healthy):
        raise ValueError(
            "The control plane and remaining workers must be Ready before replacement."
        )
    volumes = json.loads(execute([*kubectl, "get", "pv", "-o", "json"], capture=True))["items"]
    if blockers := local_volumes_for_node(volumes, node):
        raise ValueError(
            f"Migrate or back up node-local volumes before replacement: {', '.join(blockers)}"
        )
    plan_path = LOCAL / f"replace-{node}.tfplan"
    target = f"proxmox_virtual_environment_vm.node[{json.dumps(node)}]"
    execute([*TERRAFORM, "plan", "-input=false", f"-replace={target}", f"-out={plan_path}"])
    plan = json.loads(execute([*TERRAFORM, "show", "-json", str(plan_path)], capture=True))
    validate_replacement_plan(plan, node)
    print(
        "This destroys the selected worker's root disk and emptyDir data. "
        "No other VM is allowed to change."
    )
    if input(f"Type 'replace {node}' to continue: ").strip() != f"replace {node}":
        raise ValueError("Replacement cancelled before draining or applying.")
    node_deleted = False
    try:
        execute(
            [
                *kubectl,
                "drain",
                node,
                "--ignore-daemonsets",
                "--delete-emptydir-data",
                "--timeout=300s",
            ]
        )
        execute([*TERRAFORM, "apply", "-input=false", str(plan_path)])
        execute([*kubectl, "delete", "node", node])
        node_deleted = True
        password_secret = f"{node}.node-password.k3s"
        remaining = execute(
            [
                *kubectl,
                "-n",
                "kube-system",
                "get",
                "secret",
                password_secret,
                "--ignore-not-found",
                "-o",
                "name",
            ],
            capture=True,
        )
        if remaining.strip():
            execute(
                [
                    *kubectl,
                    "-n",
                    "kube-system",
                    "wait",
                    "--for=delete",
                    f"secret/{password_secret}",
                    "--timeout=60s",
                ]
            )
    finally:
        if not node_deleted:
            subprocess.run([*kubectl, "uncordon", node], check=False)
    generate_inventory()
    print(
        "Verify the new SSH host fingerprint through the Proxmox console, then run make configure."
    )


def verify_live() -> None:
    inventory = json.loads((LOCAL / "inventory.json").read_text(encoding="utf-8"))
    hosts = validate_inventory(inventory)
    settings = load_settings()
    kubectl = ["kubectl", "--kubeconfig", str(LOCAL / "kubeconfig")]
    nodes = json.loads(execute([*kubectl, "get", "nodes", "-o", "json"], capture=True))["items"]
    if {item["metadata"]["name"] for item in nodes} != set(hosts):
        raise ValueError("The live cluster does not contain exactly the four declared nodes.")
    if not all(node_ready(item) for item in nodes):
        raise ValueError("All four Kubernetes nodes must be Ready.")
    if any(
        item["status"]["nodeInfo"]["kubeletVersion"] != settings["k3s_version"] for item in nodes
    ):
        raise ValueError("Every node must run the declared K3s version.")
    namespace = settings["monitoring_namespace"]
    workloads = json.loads(
        execute(
            [
                *kubectl,
                "-n",
                namespace,
                "get",
                "deployment,statefulset,daemonset",
                "-o",
                "json",
            ],
            capture=True,
        )
    )["items"]
    if len(workloads) < 6:
        raise ValueError(
            "Expected Grafana, Prometheus, Alertmanager, operator, and metrics exporters."
        )
    for item in workloads:
        if item["kind"] == "DaemonSet":
            desired = item.get("status", {}).get("desiredNumberScheduled", 0)
            ready = item.get("status", {}).get("numberReady", 0)
        else:
            desired = item["spec"].get("replicas", 1)
            ready = item.get("status", {}).get("readyReplicas", 0)
        if desired < 1 or ready < desired:
            raise ValueError(f"Monitoring workload is not ready: {item['metadata']['name']}")
    claims = json.loads(
        execute(
            [
                *kubectl,
                "-n",
                namespace,
                "get",
                "pvc",
                "-o",
                "json",
            ],
            capture=True,
        )
    )["items"]
    if len(claims) < 3 or any(item.get("status", {}).get("phase") != "Bound" for item in claims):
        raise ValueError("Prometheus, Grafana, and Alertmanager volumes must be Bound.")
    prefix = f"/api/v1/namespaces/{namespace}/services/http:"
    grafana = json.loads(
        execute(
            [
                *kubectl,
                "get",
                "--raw",
                prefix + "monitoring-grafana:80/proxy/api/health",
            ],
            capture=True,
        )
    )
    if grafana.get("database") != "ok":
        raise ValueError("Grafana's database health check failed.")
    targets = json.loads(
        execute(
            [
                *kubectl,
                "get",
                "--raw",
                prefix + "monitoring-prometheus:9090/proxy/api/v1/targets",
            ],
            capture=True,
        )
    )["data"]["activeTargets"]
    if not targets or any(target.get("health") != "up" for target in targets):
        raise ValueError("Prometheus scrape targets are absent or unhealthy; inspect /targets.")
    execute(
        [
            "helm",
            "test",
            settings["monitoring_release_name"],
            "--namespace",
            namespace,
            "--kubeconfig",
            str(LOCAL / "kubeconfig"),
            "--timeout",
            "5m",
        ]
    )
    print(
        "Live checks passed: four Ready nodes, pinned K3s, monitoring workloads, "
        "PVCs, health, and scrape targets."
    )


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Homelab validation and guarded operations")
    commands = parser.add_subparsers(dest="command", required=True)
    crds_parser = commands.add_parser("chart-crds", help="Convert chart CRDs from YAML 1.2 to JSON")
    crds_parser.add_argument("chart", type=str)
    crds_parser.add_argument("--version")
    commands.add_parser("inventory", help="Generate a validated, private inventory from Terraform")
    commands.add_parser("vault", help="Create encrypted credentials without a plaintext file")
    commands.add_parser("chart-check", help="Verify, lint, and render the pinned monitoring chart")
    commands.add_parser("verify", help="Run live cluster and monitoring acceptance checks")
    replacement = commands.add_parser(
        "replace-worker", help="Plan and explicitly confirm a worker replacement"
    )
    replacement.add_argument("--node", required=True)
    idempotence = commands.add_parser(
        "idempotence-check", help="Check second-run Ansible JSON statistics"
    )
    idempotence.add_argument("report", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.command == "chart-crds":
            print(json.dumps(chart_crds(arguments.chart, arguments.version)))
        elif arguments.command == "inventory":
            generate_inventory()
        elif arguments.command == "vault":
            create_vault(LOCAL / "vault.yml")
        elif arguments.command == "chart-check":
            check_chart()
        elif arguments.command == "verify":
            verify_live()
        elif arguments.command == "replace-worker":
            replace_worker(arguments.node)
        elif arguments.command == "idempotence-check":
            inventory = json.loads((LOCAL / "inventory.json").read_text(encoding="utf-8"))
            report = json.loads(arguments.report.read_text(encoding="utf-8"))
            validate_idempotence(report, set(validate_inventory(inventory)))
            print(
                "Second Ansible run passed: zero changes, failures, unreachable, "
                "rescued, or ignored tasks."
            )
    except (ValueError, OSError, subprocess.CalledProcessError, YAMLError) as error:
        print(f"homelab: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
