from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
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
        macs = [host["libvirt_mac"] for host in hosts.values()]
        if len(set(addresses)) != 4 or len(set(macs)) != 4:
            raise ValueError("VM addresses and MACs must be unique.")
        if any(host["libvirt_name"] != name for name, host in hosts.items()):
            raise ValueError("Libvirt identities must match the generated node names.")
        if any(not re.fullmatch(r"52:54:00:(?:[0-9a-f]{2}:){2}[0-9a-f]{2}", mac) for mac in macs):
            raise ValueError("Invalid libvirt MAC address.")
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
    password = secrets.token_urlsafe(32)
    plaintext = json.dumps(
        {
            "k3s_token": secrets.token_hex(32),
            "grafana_admin_password": secrets.token_urlsafe(32),
            "authelia_password": password,
            "authelia_password_hash": PasswordHasher().hash(password),
            "authelia_session_secret": secrets.token_hex(32),
            "authelia_storage_key": secrets.token_hex(32),
            "authelia_jwt_secret": secrets.token_hex(32),
        }
    )
    ciphertext = execute(
        ["ansible-vault", "encrypt", "--output", "-"], capture=True, stdin=plaintext
    )
    if not ciphertext.startswith("$ANSIBLE_VAULT;"):
        raise ValueError("Vault encryption did not produce an Ansible Vault document.")
    private_write(target, ciphertext, overwrite=False)
    print("Created encrypted .local/vault.yml; plaintext credentials were never written to disk.")


def create_fitness_credentials(target: Path, password_file: Path) -> None:
    if target.is_symlink() or target.parent.is_symlink() or password_file.is_symlink():
        raise ValueError("Refusing to access vault credentials through a symlink.")
    plaintext = execute(
        ["ansible-vault", "view", str(target), "--vault-password-file", str(password_file)],
        capture=True,
    )
    try:
        documents = parse_yaml_documents(plaintext)
        if len(documents) != 1:
            raise ValueError("Expected one encrypted vault document.")
        document = documents[0]
    except (ValueError, YAMLError):
        raise ValueError("The existing encrypted vault is not a valid object.") from None
    fields = {
        "fitness_tracker_password",
        "fitness_tracker_password_hash",
        "fitness_tracker_api_token",
    }
    if fields.intersection(document):
        if not fields.issubset(document):
            raise ValueError("Fitness credentials are incomplete; restore them deliberately.")
        print("Existing encrypted fitness credentials preserved.")
        return
    password = secrets.token_urlsafe(32)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000).hex()
    document.update(
        {
            "fitness_tracker_password": password,
            "fitness_tracker_password_hash": f"pbkdf2_sha256$600000${salt.hex()}${digest}",
            "fitness_tracker_api_token": secrets.token_urlsafe(32),
        }
    )
    ciphertext = execute(
        ["ansible-vault", "encrypt", "--output", "-", "--vault-password-file", str(password_file)],
        capture=True,
        stdin=json.dumps(document),
    )
    if not ciphertext.startswith("$ANSIBLE_VAULT;"):
        raise ValueError("Credential encryption failed; the original vault was not changed.")
    private_write(target, ciphertext)
    print("Fitness credentials added to the encrypted vault; existing cluster identity preserved.")


def create_pki(domain: str) -> None:
    if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)+", domain):
        raise ValueError("Use an ASCII DNS domain for internal TLS.")
    directory = LOCAL / "pki"
    certificate_path = directory / "tls.crt"
    if certificate_path.exists():
        certificate = x509.load_pem_x509_certificate(certificate_path.read_bytes())
        names = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        if f"*.{domain}" not in names.get_values_for_type(x509.DNSName):
            raise ValueError(
                "Existing TLS certificate belongs to another domain; rotate deliberately."
            )
        if certificate.not_valid_after_utc <= datetime.now(UTC) + timedelta(days=30):
            raise ValueError(
                "Internal TLS certificate expires within 30 days; rotate it deliberately."
            )
        if not all((directory / name).is_file() for name in ("ca.crt", "ca.key", "tls.key")):
            raise ValueError("Existing PKI is incomplete; restore its original private files.")
        return
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Refusing to overwrite an incomplete existing PKI.")
    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "PN51 Homelab CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    tls_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"*.{domain}")]))
        .issuer_name(ca_name)
        .public_key(tls_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(domain), x509.DNSName(f"*.{domain}")]),
            critical=False,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    for name, key in (("ca.key", ca_key), ("tls.key", tls_key)):
        private_write(
            directory / name,
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode(),
            overwrite=False,
        )
    for name, item in (("ca.crt", ca), ("tls.crt", certificate)):
        private_write(
            directory / name,
            item.public_bytes(serialization.Encoding.PEM).decode(),
            overwrite=False,
        )


def initialize_local(public_key: Path | None = None) -> None:
    if public_key is None:
        config = execute(["ssh", "-G", "pn51"], capture=True)
        identities = [
            line.split(maxsplit=1)[1]
            for line in config.splitlines()
            if line.startswith("identityfile ")
        ]
        public_key = next(
            (
                Path(f"{identity}.pub").expanduser()
                for identity in identities
                if Path(f"{identity}.pub").expanduser().is_file()
            ),
            None,
        )
    if public_key is None or public_key.suffix != ".pub":
        raise ValueError(
            "Provide the existing PN51 SSH public key with --public-key; never a private key."
        )
    key = public_key.read_text().strip()
    if not re.fullmatch(
        r"(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp[0-9]+) [A-Za-z0-9+/=]+(?: .*)?", key
    ):
        raise ValueError("Invalid OpenSSH public key.")
    inputs = LOCAL / "terraform.tfvars.json"
    if not inputs.exists():
        private_write(
            inputs, json.dumps({"ssh_public_keys": [key]}, indent=2) + "\n", overwrite=False
        )
    password_file = LOCAL / "vault-password"
    if not password_file.exists():
        if (LOCAL / "vault.yml").exists():
            raise ValueError(
                "Existing vault needs its original password, not a newly generated one."
            )
        private_write(password_file, secrets.token_urlsafe(48) + "\n", overwrite=False)
    if not (LOCAL / "vault.yml").exists():
        previous = os.environ.get("ANSIBLE_VAULT_PASSWORD_FILE")
        os.environ["ANSIBLE_VAULT_PASSWORD_FILE"] = str(password_file)
        try:
            create_vault(LOCAL / "vault.yml")
        finally:
            if previous is None:
                os.environ.pop("ANSIBLE_VAULT_PASSWORD_FILE", None)
            else:
                os.environ["ANSIBLE_VAULT_PASSWORD_FILE"] = previous
    create_pki(load_settings()["lab_domain"])
    print("Private Terraform inputs, encrypted vault, vault password, and internal PKI are ready.")


def download_image() -> None:
    manifest = json.loads((ROOT / "pn51/terraform/image.json").read_text())
    directory = LOCAL / "images"
    if directory.is_symlink() or LOCAL.is_symlink():
        raise ValueError("Refusing to download through a symlink.")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory / manifest["name"]
    if target.is_symlink():
        raise ValueError("Refusing to replace a linked image.")
    if target.exists():
        with target.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != manifest["sha256"]:
            raise ValueError("Existing Ubuntu image checksum mismatch; inspect it before retrying.")
        print("Pinned Ubuntu image is already present and verified.")
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
            temporary = Path(output.name)
        execute(
            [
                "/usr/bin/curl",
                "--disable",
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--proto",
                "=https",
                "--proto-redir",
                "=https",
                "--connect-timeout",
                "30",
                "--max-time",
                "900",
                "--output",
                str(temporary),
                manifest["url"],
            ]
        )
        with temporary.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != manifest["sha256"]:
            raise ValueError("Downloaded Ubuntu image checksum mismatch; no image was installed.")
        temporary.chmod(0o600)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print("Downloaded and SHA-256-verified the pinned Ubuntu server image.")


def remote_virsh(alias: str, arguments: list[str]) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", alias):
        raise ValueError("Invalid PN51 SSH alias.")
    return execute(
        [
            "ssh",
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UpdateHostKeys=no",
            "-o",
            "ControlPath=none",
            alias,
            shlex.join(["virsh", "--connect", "qemu:///system", *arguments]),
        ],
        capture=True,
    )


def trust_guest_keys() -> None:
    inventory = json.loads((LOCAL / "inventory.json").read_text())
    hosts = validate_inventory(inventory)
    alias = inventory["all"]["vars"]["pn51_host_ssh_alias"]
    lines = []
    for name, host in sorted(hosts.items()):
        domain = ET.fromstring(remote_virsh(alias, ["dumpxml", name]))
        interfaces = domain.findall("./devices/interface")
        if not any(
            interface.find("mac") is not None
            and interface.find("mac").get("address") == host["libvirt_mac"]
            for interface in interfaces
        ):
            raise ValueError(f"VM {name} does not have the Terraform-declared MAC.")
        deadline = time.monotonic() + 900
        request = json.dumps(
            {
                "execute": "guest-exec",
                "arguments": {
                    "path": "/usr/bin/cat",
                    "arg": ["/etc/ssh/ssh_host_ed25519_key.pub"],
                    "capture-output": True,
                },
            }
        )
        while True:
            try:
                result = json.loads(remote_virsh(alias, ["qemu-agent-command", name, request]))
                pid = result["return"]["pid"]
                break
            except subprocess.CalledProcessError:
                if time.monotonic() >= deadline:
                    raise ValueError(f"Guest agent did not become ready on {name}.") from None
                time.sleep(5)
        while True:
            result = json.loads(
                remote_virsh(
                    alias,
                    [
                        "qemu-agent-command",
                        name,
                        json.dumps({"execute": "guest-exec-status", "arguments": {"pid": pid}}),
                    ],
                )
            )["return"]
            if result.get("exited"):
                break
            if time.monotonic() >= deadline:
                raise ValueError(f"Guest key retrieval timed out on {name}.")
            time.sleep(1)
        if result.get("exitcode") != 0:
            raise ValueError(f"Guest SSH key was not available on {name}.")
        key = base64.b64decode(result["out-data"], validate=True).decode().strip()
        if not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/=]+(?: .*)?", key):
            raise ValueError(f"Invalid guest SSH public key on {name}.")
        lines.append(f"{host['ansible_host']},{name} {key}")
    private_write(LOCAL / "known_hosts", "\n".join(lines) + "\n")
    print("Verified all four guest SSH keys through the authenticated PN51 libvirt connection.")


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


def validate_platform(documents: list[dict[str, Any]]) -> None:
    ingresses = [item for item in documents if item.get("kind") == "Ingress"]
    if {item["metadata"]["name"] for item in ingresses} != {
        "auth",
        "headlamp",
        "grafana",
        "prometheus",
        "alertmanager",
        "homepage",
        "argocd",
    }:
        raise ValueError("Expected exactly seven secured platform routes.")
    for item in ingresses:
        if not item["spec"].get("tls") or item["spec"].get("ingressClassName") != "traefik":
            raise ValueError("Every platform ingress must use TLS and Traefik.")
        annotations = item["metadata"].get("annotations", {})
        middleware = annotations.get("traefik.ingress.kubernetes.io/router.middlewares", "")
        if item["metadata"]["name"] != "auth" and "-authelia@kubernetescrd" not in middleware:
            raise ValueError("Every dashboard must require Authelia authentication.")
    deployments = [item for item in documents if item.get("kind") == "Deployment"]
    if {item["metadata"]["name"] for item in deployments} != {"authelia", "headlamp", "homepage"}:
        raise ValueError("Expected Authelia, Headlamp, and Homepage deployments.")
    for item in deployments:
        pod = item["spec"]["template"]["spec"]
        if pod.get("enableServiceLinks", True):
            raise ValueError("Platform service-link environment injection must be disabled.")
        if item["metadata"]["name"] == "homepage":
            if pod.get("automountServiceAccountToken", True):
                raise ValueError("Homepage must not receive Kubernetes credentials.")
            environment = {
                entry["name"]: entry.get("value") for entry in pod["containers"][0].get("env", [])
            }
            route = next(route for route in ingresses if route["metadata"]["name"] == "homepage")
            if environment.get("HOMEPAGE_ALLOWED_HOSTS") != route["spec"]["rules"][0]["host"]:
                raise ValueError("Homepage must accept only its declared ingress hostname.")
        if not pod.get("securityContext", {}).get("runAsNonRoot"):
            raise ValueError("Platform containers must run without root.")
        for container in pod["containers"]:
            if container["name"] == "authelia" and container.get("args", [])[:1] != ["authelia"]:
                raise ValueError("Authelia's image entrypoint requires the executable in its args.")
            security = container.get("securityContext", {})
            if (
                security.get("allowPrivilegeEscalation", True)
                or not security.get("readOnlyRootFilesystem")
                or security.get("capabilities", {}).get("drop") != ["ALL"]
            ):
                raise ValueError("Platform containers require restricted security contexts.")
            if (
                ":latest" in container["image"]
                or "@sha256:" not in container["image"]
                and ":" not in container["image"]
            ):
                raise ValueError("Platform images must be explicitly version-pinned.")
    for item in documents:
        if item.get("kind") == "ClusterRoleBinding" and item["roleRef"]["name"] == "cluster-admin":
            raise ValueError("Headlamp must not receive cluster-admin by default.")
        if (
            item.get("kind") == "Secret"
            and item.get("type") == "kubernetes.io/service-account-token"
        ):
            raise ValueError("Do not issue persistent Headlamp bearer tokens.")
        if item.get("kind") == "Service" and item["spec"].get("type", "ClusterIP") != "ClusterIP":
            raise ValueError("Platform services must stay private behind ingress.")
    if len([item for item in documents if item.get("kind") == "NetworkPolicy"]) < 2:
        raise ValueError("Platform and monitoring need explicit network policies.")


def check_platform_templates() -> None:
    directory = LOCAL / "test-templates"
    documents = parse_yaml_documents((directory / "platform-resources.yml").read_text())
    validate_platform(documents)
    fixture = parse_yaml_documents((directory / "authelia-fixture.yml").read_text())[0]
    configuration = parse_yaml_documents(fixture["stringData"]["configuration.yml"])[0]
    if not configuration["server"].get("disable_healthcheck"):
        raise ValueError("Read-only Authelia pods must not generate Docker healthcheck metadata.")
    control = configuration["access_control"]
    if control["default_policy"] != "deny" or any(
        rule["policy"] != "two_factor" for rule in control["rules"]
    ):
        raise ValueError("Authelia must default-deny and require two-factor authentication.")
    print(
        f"Validated {len(documents)} platform resources, MFA protection, "
        "restricted pods, and read-only RBAC."
    )


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


def validate_argocd(documents: list[dict[str, Any]]) -> None:
    crds = {
        item["metadata"]["name"]
        for item in documents
        if item.get("kind") == "CustomResourceDefinition"
    }
    if crds != {
        "applications.argoproj.io",
        "applicationsets.argoproj.io",
        "appprojects.argoproj.io",
    }:
        raise ValueError("The pinned Argo CD chart must declare its three reviewed CRDs.")
    for item in documents:
        if item.get("kind") == "Service" and item["spec"].get("type", "ClusterIP") != "ClusterIP":
            raise ValueError("Argo CD services must remain private ClusterIP services.")
        if item.get("kind") == "Ingress":
            raise ValueError("Argo CD ingress is owned by the secured platform, not the chart.")
        if item.get("kind") == "NetworkPolicy" and item["metadata"]["name"] == "argocd-server":
            raise ValueError("Do not install the chart unrestricted Argo server ingress policy.")
    configmaps = {
        item["metadata"]["name"]: item.get("data", {})
        for item in documents
        if item.get("kind") == "ConfigMap"
    }
    if str(configmaps["argocd-cm"].get("users.anonymous.enabled")).lower() != "false":
        raise ValueError("Anonymous Argo CD access must stay disabled.")
    if configmaps["argocd-rbac-cm"].get("policy.default") != "role:readonly":
        raise ValueError("Default Argo CD user permissions must be read-only.")
    workloads = [item for item in documents if item.get("kind") in {"Deployment", "StatefulSet"}]
    expected = {
        "argocd-server",
        "argocd-repo-server",
        "argocd-redis",
        "argocd-application-controller",
    }
    if not expected.issubset({item["metadata"]["name"] for item in workloads}):
        raise ValueError(
            "Expected the Argo CD server, repository, cache, and controller workloads."
        )
    for item in workloads:
        pod = item["spec"]["template"]["spec"]
        for container in pod["containers"]:
            security = container.get("securityContext", {})
            if security.get("allowPrivilegeEscalation", True) or not security.get(
                "readOnlyRootFilesystem"
            ):
                raise ValueError("Argo CD workloads need restricted container security contexts.")
            if not security.get("runAsNonRoot", pod.get("securityContext", {}).get("runAsNonRoot")):
                raise ValueError("Argo CD workloads must run without root.")


def check_argocd_chart() -> None:
    settings = load_settings()
    version = settings["argocd_chart_version"]
    archive = LOCAL / f"argo-cd-{version}.tgz"
    LOCAL.mkdir(mode=0o700, exist_ok=True)
    if not archive.exists():
        execute(
            [
                "helm",
                "pull",
                "argo-cd",
                "--repo",
                "https://argoproj.github.io/argo-helm",
                "--version",
                version,
                "--destination",
                str(LOCAL),
            ]
        )
    expected = settings["argocd_chart_checksum"].removeprefix("sha256:")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise ValueError("Argo CD chart checksum mismatch; inspect the archive before retrying.")
    values = ROOT / "pn51/gitops/values.yml"
    kubernetes_version = settings["k3s_version"].removeprefix("v").split("+")[0]
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
            "argocd",
            str(archive),
            "--namespace",
            settings["argocd_namespace"],
            "--kube-version",
            kubernetes_version,
            "--values",
            str(values),
            "--include-crds",
        ],
        capture=True,
    )
    documents = parse_yaml_documents(rendered)
    validate_argocd(documents)
    projects = parse_yaml_documents((LOCAL / "test-templates/argocd-projects.yml").read_text())
    validate_argocd_projects(projects, settings)
    print(
        f"Validated {len(documents)} pinned Argo CD resources, private access, "
        "and application-only project scope."
    )


def validate_argocd_projects(projects: list[dict[str, Any]], settings: dict[str, Any]) -> None:
    by_name = {item["metadata"]["name"]: item["spec"] for item in projects}
    if by_name["default"].get("sourceRepos") or by_name["default"].get("destinations"):
        raise ValueError(
            "The default Argo CD project must not permit arbitrary repositories or destinations."
        )
    project = by_name["homelab"]
    if project["sourceRepos"] != [settings["argocd_application_repository"]] or project[
        "destinations"
    ] != [
        {
            "server": "https://kubernetes.default.svc",
            "namespace": settings["argocd_application_namespace"],
        }
    ]:
        raise ValueError(
            "Scope the homelab project to the reviewed repository and application namespace."
        )
    if project.get("clusterResourceWhitelist"):
        raise ValueError("Application GitOps must not manage cluster-scoped infrastructure.")
    if not any(
        rule.get("group") in {"", "*"} and rule.get("kind") in {"Secret", "*"}
        for rule in project.get("namespaceResourceBlacklist", [])
    ):
        raise ValueError("Application GitOps must not own Ansible-managed runtime Secrets.")


def validate_fitness_workload(
    documents: list[dict[str, Any]], *, allow_unreleased: bool = False
) -> None:
    settings = load_settings()
    namespace = settings["argocd_application_namespace"]
    if any(item["metadata"].get("namespace") != namespace for item in documents):
        raise ValueError("Every fitness resource must stay in the admitted application namespace.")
    if any(
        item["kind"] in {"Secret", "Namespace", "ClusterRole", "ClusterRoleBinding"}
        for item in documents
    ):
        raise ValueError(
            "Application GitOps must not publish credentials or cluster infrastructure."
        )
    deployments = {
        item["metadata"]["name"]: item for item in documents if item["kind"] == "Deployment"
    }
    if set(deployments) != {"fitness-tracker-backend", "fitness-tracker-frontend"}:
        raise ValueError("Declare the existing backend/frontend split explicitly.")
    backend = deployments["fitness-tracker-backend"]["spec"]
    if backend["replicas"] != 1 or backend.get("strategy", {}).get("type") != "Recreate":
        raise ValueError("SQLite requires one backend writer and a Recreate rollout.")
    for component in ("backend", "frontend"):
        pod = deployments[f"fitness-tracker-{component}"]["spec"]["template"]["spec"]
        if pod.get("automountServiceAccountToken", True) or pod.get("enableServiceLinks", True):
            raise ValueError("Fitness pods must not receive API tokens or service-link injection.")
        if not pod.get("securityContext", {}).get("runAsNonRoot"):
            raise ValueError("Fitness containers must run without root.")
        container = pod["containers"][0]
        security = container.get("securityContext", {})
        if (
            security.get("allowPrivilegeEscalation", True)
            or not security.get("readOnlyRootFilesystem")
            or security.get("capabilities", {}).get("drop") != ["ALL"]
        ):
            raise ValueError("Fitness containers require restricted security contexts.")
        repository = "ghcr.io/thenewthinktank/fitness-tracker" + (
            "-frontend" if component == "frontend" else ""
        )
        image = container["image"]
        if not re.fullmatch(re.escape(repository) + r"@sha256:[a-f0-9]{64}", image):
            if not (allow_unreleased and image == repository + ":release-required"):
                raise ValueError("Publish and pin both fitness images by digest before deployment.")
        if any(
            "hostPath" in volume or "nfs" in volume or "secret" in volume
            for volume in pod.get("volumes", [])
        ):
            raise ValueError(
                "Use retained local state, not host paths or imported Google credentials."
            )
    configuration = next(item["data"] for item in documents if item["kind"] == "ConfigMap")
    expected = {
        "FITNESS_TRACKER_DATA_DIR": "/data",
        "FITNESS_TRACKER_STATE_DIR": "/state",
        "FITNESS_TRACKER_AUTH_REQUIRED": "true",
        "FITNESS_TRACKER_COOKIE_SECURE": "true",
        "FITNESS_TRACKER_ENABLE_WRITES": "true",
        "PYTHON_DOTENV_DISABLED": "1",
    }
    if any(configuration.get(key) != value for key, value in expected.items()):
        raise ValueError(
            "Keep local state, secure athlete sessions, writes, and dotenv isolation explicit."
        )
    if any("GOOGLE" in key or "CREDENTIALS" in key for key in configuration):
        raise ValueError("Google integrations are not part of this deployment.")
    claims = [item for item in documents if item["kind"] == "PersistentVolumeClaim"]
    if (
        len(claims) != 1
        or claims[0]["spec"]["storageClassName"] != settings["monitoring_storage_class"]
        or claims[0]["spec"]["accessModes"] != ["ReadWriteOnce"]
    ):
        raise ValueError("The single SQLite state volume must use retained node-local storage.")
    backend_volumes = backend["template"]["spec"]["volumes"]
    if not any(
        volume.get("persistentVolumeClaim", {}).get("claimName") == claims[0]["metadata"]["name"]
        for volume in backend_volumes
    ):
        raise ValueError("Attach the retained state claim to the backend.")
    mounts = {
        mount["name"]: mount
        for mount in backend["template"]["spec"]["containers"][0]["volumeMounts"]
    }
    if mounts.get("state", {}).get("mountPath") != "/state" or mounts["state"].get(
        "readOnly", False
    ):
        raise ValueError("Keep SQLite writable only on the separate retained state volume.")
    if mounts.get("imported-data", {}).get("mountPath") != "/data" or not mounts[
        "imported-data"
    ].get("readOnly"):
        raise ValueError("Imported YAML must remain read-only and separate from SQLite state.")
    for item in documents:
        if item["kind"] == "Service" and item["spec"].get("type", "ClusterIP") != "ClusterIP":
            raise ValueError("Expose fitness only through the authenticated ingress.")
    ingress = next(item for item in documents if item["kind"] == "Ingress")
    if (
        not ingress["spec"].get("tls")
        or ingress["spec"]["rules"][0]["host"] != "fitness." + settings["lab_domain"]
    ):
        raise ValueError("The app must use the declared private HTTPS hostname.")
    if "fitness-tracker-authelia@kubernetescrd" not in ingress["metadata"]["annotations"].get(
        "traefik.ingress.kubernetes.io/router.middlewares", ""
    ):
        raise ValueError("Fitness ingress must require Authelia MFA.")
    policies = [item for item in documents if item["kind"] == "NetworkPolicy"]
    if len(policies) != 1 or set(policies[0]["spec"]["policyTypes"]) != {"Ingress", "Egress"}:
        raise ValueError("The app needs an explicit ingress/egress boundary.")
    for rule in policies[0]["spec"].get("egress", []):
        peers = rule.get("to", [])
        ports = rule.get("ports", [])
        if not peers or not ports or any("endPort" in port for port in ports):
            raise ValueError("Fitness may reach only cluster DNS and its local API, not Google.")
        for peer in peers:
            if peer == {
                "namespaceSelector": {
                    "matchLabels": {"kubernetes.io/metadata.name": "kube-system"}
                },
                "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
            }:
                allowed_ports = {("UDP", 53), ("TCP", 53)}
            elif peer == {
                "podSelector": {
                    "matchLabels": {
                        "app.kubernetes.io/name": "fitness-tracker",
                        "app.kubernetes.io/component": "backend",
                    }
                }
            }:
                allowed_ports = {("TCP", 8000)}
            else:
                raise ValueError("Fitness egress must target only CoreDNS or its own backend.")
            if not {(port.get("protocol", "TCP"), port["port"]) for port in ports}.issubset(
                allowed_ports
            ):
                raise ValueError(
                    "Fitness egress ports must match their declared local destination."
                )


def check_fitness_workload(*, allow_unreleased: bool = False) -> None:
    rendered = execute(
        ["kubectl", "kustomize", str(ROOT / "pn51/dev/fitness-tracker-k8s")], capture=True
    )
    documents = parse_yaml_documents(rendered)
    validate_fitness_workload(documents, allow_unreleased=allow_unreleased)
    print(f"Validated {len(documents)} restricted local-data fitness resources.")


def deploy_fitness() -> None:
    check_fitness_workload()
    settings = load_settings()
    application = parse_yaml_documents((ROOT / "pn51/application.yaml").read_text())[0]
    source = application["spec"]["source"]
    if (
        source.get("repoURL") != settings["argocd_application_repository"]
        or source.get("path") != "pn51/dev/fitness-tracker-k8s"
        or source.get("targetRevision") not in {"HEAD", "main"}
    ):
        raise ValueError(
            "The Application must track the reviewed HTTPS repository and workload path."
        )
    paths = ["pn51/dev/fitness-tracker-k8s", "pn51/application.yaml"]
    if execute(
        ["git", "-C", str(ROOT), "status", "--porcelain", "--", *paths], capture=True
    ).strip():
        raise ValueError(
            "Commit and publish the reviewed fitness manifests before Argo CD deployment."
        )
    revision = execute(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture=True).strip()
    published = execute(
        ["git", "-C", str(ROOT), "ls-remote", source["repoURL"], "refs/heads/main"], capture=True
    ).split()
    if not published or published[0] != revision:
        raise ValueError("Publish the reviewed homelab revision before creating the Application.")
    kubectl = ["kubectl", "--kubeconfig", str(LOCAL / "kubeconfig")]
    execute(
        [
            *kubectl,
            "-n",
            "fitness-tracker",
            "get",
            "secret",
            "fitness-tracker-runtime",
            "homelab-tls",
            "-o",
            "name",
        ]
    )
    execute([*kubectl, "apply", "-f", str(ROOT / "pn51/application.yaml")])
    print(
        "Argo CD Application created from the published repository; no workload applied directly."
    )


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
        data_path = specification.get("hostPath", specification.get("local", {})).get("path", "")
        retained_data = os.path.normpath(data_path).startswith("/srv/homelab-data/storage/")
        if (attached or uncertain_local) and not (attached and retained_data):
            blockers.append(volume["metadata"]["name"])
    return blockers


def validate_replacement_plan(plan: dict[str, Any], node: str) -> None:
    suffix = f"[{json.dumps(node)}]"
    target = "libvirt_domain.node" + suffix
    disk = "libvirt_volume.node" + suffix
    allowed = {
        target,
        disk,
        "libvirt_cloudinit_disk.node" + suffix,
    }
    replacement = False
    disk_replacement = False
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
        if resource["address"] == disk:
            disk_replacement = sorted(actions) == ["create", "delete"]
    if not replacement or not disk_replacement:
        raise ValueError(
            "Expected an explicit replacement of the selected worker VM and root disk."
        )


def node_ready(node: dict[str, Any]) -> bool:
    return any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in node.get("status", {}).get("conditions", [])
    )


def replace_worker(node: str, confirmation: str | None = None) -> None:
    inventory = json.loads((LOCAL / "inventory.json").read_text(encoding="utf-8"))
    hosts = validate_inventory(inventory)
    groups = inventory["all"]["children"]["k3s_cluster"]["children"]
    if node not in groups["k3s_agents"]["hosts"]:
        raise ValueError(
            "Only a generated worker name may be replaced; "
            "control-plane replacement needs a restore."
        )
    expected_confirmation = f"replace {node}"
    if confirmation is not None and confirmation.strip() != expected_confirmation:
        raise ValueError("Replacement confirmation must exactly match the selected worker.")
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
    target = f"libvirt_domain.node[{json.dumps(node)}]"
    disk = f"libvirt_volume.node[{json.dumps(node)}]"
    execute(
        [
            *TERRAFORM,
            "plan",
            "-input=false",
            f"-var-file={LOCAL / 'terraform.tfvars.json'}",
            f"-replace={target}",
            f"-replace={disk}",
            f"-out={plan_path}",
        ]
    )
    plan = json.loads(execute([*TERRAFORM, "show", "-json", str(plan_path)], capture=True))
    validate_replacement_plan(plan, node)
    print(
        "This destroys the selected worker's root disk and emptyDir data. "
        "No other VM is allowed to change."
    )
    answer = (
        confirmation
        if confirmation is not None
        else input(f"Type '{expected_confirmation}' to continue: ")
    )
    if answer.strip() != expected_confirmation:
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
        "Run make trust-guest-keys to verify the new SSH key through libvirt, then make configure."
    )


def workload_ready(item: dict[str, Any]) -> bool:
    if item["kind"] == "DaemonSet":
        desired = item.get("status", {}).get("desiredNumberScheduled", 0)
        ready = item.get("status", {}).get("numberReady", 0)
    else:
        desired = item["spec"].get("replicas", 1)
        ready = item.get("status", {}).get("readyReplicas", 0)
    return desired >= 1 and ready >= desired


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
        if not workload_ready(item):
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
    platform = json.loads(
        execute([*kubectl, "-n", "platform", "get", "deployment", "-o", "json"], capture=True)
    )["items"]
    if {item["metadata"]["name"] for item in platform} != {
        "authelia",
        "headlamp",
        "homepage",
    } or not all(workload_ready(item) for item in platform):
        raise ValueError("Authelia, Headlamp, and Homepage must all be available.")
    argocd_namespace = settings["argocd_namespace"]
    gitops = json.loads(
        execute(
            [*kubectl, "-n", argocd_namespace, "get", "deployment,statefulset", "-o", "json"],
            capture=True,
        )
    )["items"]
    required_gitops = {
        "argocd-server",
        "argocd-repo-server",
        "argocd-redis",
        "argocd-application-controller",
    }
    if not required_gitops.issubset({item["metadata"]["name"] for item in gitops}) or not all(
        workload_ready(item) for item in gitops
    ):
        raise ValueError(
            "All declared Argo CD controllers, server, repository, and cache must be ready."
        )
    projects = json.loads(
        execute([*kubectl, "-n", argocd_namespace, "get", "appproject", "-o", "json"], capture=True)
    )["items"]
    validate_argocd_projects(projects, settings)
    argocd_health = execute(
        [
            *kubectl,
            "get",
            "--raw",
            f"/api/v1/namespaces/{argocd_namespace}/services/http:argocd-server:80/proxy/healthz",
        ],
        capture=True,
    )
    if argocd_health.strip().lower() != "ok":
        raise ValueError("Argo CD server health check failed.")
    platform_claims = json.loads(
        execute([*kubectl, "-n", "platform", "get", "pvc", "-o", "json"], capture=True)
    )["items"]
    if not platform_claims or any(
        item.get("status", {}).get("phase") != "Bound" for item in platform_claims
    ):
        raise ValueError("Authelia persistent storage must be Bound.")
    volumes = json.loads(execute([*kubectl, "get", "pv", "-o", "json"], capture=True))["items"]
    bound_names = {item["spec"]["volumeName"] for item in claims + platform_claims}
    for item in volumes:
        if item["metadata"]["name"] not in bound_names:
            continue
        specification = item["spec"]
        data_path = os.path.normpath(specification.get("hostPath", {}).get("path", ""))
        if specification.get(
            "persistentVolumeReclaimPolicy"
        ) != "Retain" or not data_path.startswith("/srv/homelab-data/storage/"):
            raise ValueError("Application volumes must be retained on the protected data disks.")
    system = json.loads(
        execute([*kubectl, "-n", "kube-system", "get", "deployment", "-o", "json"], capture=True)
    )["items"]
    essential = {"traefik", "coredns", "metrics-server", "local-path-provisioner"}
    ready_system = {item["metadata"]["name"] for item in system if workload_ready(item)}
    if not essential.issubset(ready_system):
        raise ValueError("Traefik, DNS, metrics, and storage provisioner must be available.")
    authelia = json.loads(
        execute(
            [
                *kubectl,
                "get",
                "--raw",
                "/api/v1/namespaces/platform/services/http:authelia:9091/proxy/api/health",
            ],
            capture=True,
        )
    )
    if authelia.get("status") != "OK":
        raise ValueError("Authelia health check failed.")
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
        "retained PVCs, healthy scrape targets, Authelia, Headlamp, Homepage, "
        "scoped Argo CD, DNS, ingress, and metrics."
    )


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Homelab validation and guarded operations")
    commands = parser.add_subparsers(dest="command", required=True)
    crds_parser = commands.add_parser("chart-crds", help="Convert chart CRDs from YAML 1.2 to JSON")
    crds_parser.add_argument("chart", type=str)
    crds_parser.add_argument("--version")
    commands.add_parser("inventory", help="Generate a validated, private inventory from Terraform")
    initialize = commands.add_parser(
        "init-local", help="Prepare private inputs, encrypted credentials, and PKI"
    )
    initialize.add_argument("--public-key", type=Path)
    commands.add_parser("image", help="Download and verify the pinned Ubuntu cloud image")
    commands.add_parser(
        "trust-guest-keys", help="Verify guest SSH keys using the trusted libvirt host"
    )
    commands.add_parser("vault", help="Create encrypted credentials without a plaintext file")
    fitness_credentials = commands.add_parser(
        "fitness-credentials", help="Add local app credentials to the encrypted vault"
    )
    fitness_credentials.add_argument("--vault", type=Path, default=LOCAL / "vault.yml")
    fitness_credentials.add_argument("--password-file", type=Path, default=LOCAL / "vault-password")
    commands.add_parser("chart-check", help="Verify, lint, and render the pinned monitoring chart")
    commands.add_parser(
        "argocd-chart-check", help="Validate the pinned Argo CD chart and project boundary"
    )
    commands.add_parser("platform-check", help="Validate rendered platform security contracts")
    fitness_check = commands.add_parser(
        "fitness-check", help="Validate the local-data application manifests"
    )
    fitness_check.add_argument(
        "--allow-unreleased", action="store_true", help="Validate draft shape only; never deploy"
    )
    commands.add_parser(
        "fitness-deploy", help="Create the Application only after strict release/publication checks"
    )
    commands.add_parser("verify", help="Run live cluster and monitoring acceptance checks")
    replacement = commands.add_parser(
        "replace-worker", help="Plan and explicitly confirm a worker replacement"
    )
    replacement.add_argument("--node", required=True)
    replacement.add_argument(
        "--confirm", help="Exact 'replace NODE' confirmation for approved automation"
    )
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
        elif arguments.command == "init-local":
            initialize_local(arguments.public_key)
        elif arguments.command == "image":
            download_image()
        elif arguments.command == "trust-guest-keys":
            trust_guest_keys()
        elif arguments.command == "vault":
            create_vault(LOCAL / "vault.yml")
        elif arguments.command == "fitness-credentials":
            create_fitness_credentials(arguments.vault, arguments.password_file)
        elif arguments.command == "chart-check":
            check_chart()
        elif arguments.command == "argocd-chart-check":
            check_argocd_chart()
        elif arguments.command == "platform-check":
            check_platform_templates()
        elif arguments.command == "fitness-check":
            check_fitness_workload(allow_unreleased=arguments.allow_unreleased)
        elif arguments.command == "fitness-deploy":
            deploy_fitness()
        elif arguments.command == "verify":
            verify_live()
        elif arguments.command == "replace-worker":
            replace_worker(arguments.node, confirmation=arguments.confirm)
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
