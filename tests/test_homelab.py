from __future__ import annotations

import copy
import io
import json
import os
import re
import stat
import subprocess
from pathlib import Path

import pycdlib
import pytest
import yaml
from ansible.plugins.become.sudo import BecomeModule
from cryptography import x509
from ruamel.yaml.error import YAMLError

from scripts import homelab

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def inventory():
    return yaml.safe_load((ROOT / "pn51/ansible/inventory.example.yml").read_text())


def test_yaml_12_crd_scalar_regression():
    documents = homelab.parse_yaml_documents("enum: [=, '!=', on, off]\nenabled: true\n")
    assert documents == [{"enum": ["=", "!=", "on", "off"], "enabled": True}]


def test_yaml_object_construction_remains_forbidden():
    with pytest.raises(YAMLError):
        homelab.parse_yaml_documents("!!python/object/apply:os.system ['false']")


def test_yaml_root_must_be_an_object():
    with pytest.raises(ValueError, match="object"):
        homelab.parse_yaml_documents("[one, two]")


def test_generated_inventory_contract(inventory):
    assert len(homelab.validate_inventory(inventory)) == 4


def test_host_sudo_prompt_compatibility_is_scoped(inventory):
    become = BecomeModule()
    become.prompt = "[sudo via ansible, key=fixture] password:"
    assert not become.check_password_prompt(f"[sudo: {become.prompt}] Password: ".encode())
    assert become.check_password_prompt(become.prompt.encode())
    source = ROOT / "pn51/ansible/host-inventory.yml"
    host = yaml.safe_load(source.read_text())["all"]["children"]["pn51_host"]["hosts"]["pn51"]
    assert host["ansible_become_exe"] == "/usr/bin/sudo.ws"
    assert "ansible_become_exe" not in inventory["all"]["vars"]


def test_ubuntu_host_selects_a_concrete_kvm_provider():
    source = ROOT / "pn51/ansible/host.yml"
    play = yaml.safe_load(source.read_text())[0]
    installation = next(
        task["ansible.builtin.apt"] for task in play["tasks"] if "ansible.builtin.apt" in task
    )
    assert "qemu-system-x86" in installation["name"]
    assert "qemu-kvm" not in installation["name"]


def test_host_storage_directory_is_private_to_qemu_and_administrators():
    source = ROOT / "pn51/ansible/host.yml"
    play = yaml.safe_load(source.read_text())[0]
    directory = next(
        task["ansible.builtin.file"]
        for task in play["tasks"]
        if task.get("ansible.builtin.file", {}).get("path") == "/var/lib/libvirt/homelab"
    )
    assert directory["owner"] == "libvirt-qemu"
    assert directory["group"] == "libvirt"
    assert int(directory["mode"], 8) == 0o750


def test_guest_package_management_waits_for_security_updates():
    source = ROOT / "pn51/ansible/roles/baseline/tasks/main.yml"
    tasks = yaml.safe_load(source.read_text())
    installation = next(
        task["ansible.builtin.apt"] for task in tasks if "ansible.builtin.apt" in task
    )
    assert installation["lock_timeout"] == 600


def test_protected_kernel_defaults_match_pinned_kubelet():
    source = ROOT / "pn51/ansible/roles/baseline/tasks/main.yml"
    tasks = yaml.safe_load(source.read_text())
    task = next(item for item in tasks if "ansible.posix.sysctl" in item)
    settings = task["vars"]["baseline_sysctls"]
    required = {
        "vm.overcommit_memory": "1",
        "vm.panic_on_oom": "0",
        "kernel.panic": "10",
        "kernel.panic_on_oops": "1",
        "kernel.keys.root_maxkeys": "1000000",
        "kernel.keys.root_maxbytes": "25000000",
    }
    assert all(settings.get(key) == value for key, value in required.items())


def test_dotfiles_integration_is_opt_in_and_uses_a_public_source():
    role = ROOT / "pn51/ansible/roles/dotfiles"
    defaults = yaml.safe_load((role / "defaults/main.yml").read_text())
    assert defaults["dotfiles_enabled"] is False
    assert re.fullmatch(r"[a-f0-9]{40}", defaults["dotfiles_revision"])
    example = yaml.safe_load((ROOT / "pn51/ansible/config.example.yml").read_text())
    assert example["dotfiles_enabled"] is True
    assert example["dotfiles_revision"] == defaults["dotfiles_revision"]
    assert defaults["dotfiles_repository"] == "https://github.com/TheNewThinkTank/dotfiles.git"
    tasks = yaml.safe_load((role / "tasks/main.yml").read_text())
    assert tasks[0]["ansible.builtin.assert"]["that"][0] == (
        "dotfiles_revision is match('^[a-f0-9]{40}$')"
    )
    block = next(task for task in tasks if "block" in task)
    assert block["become_user"] == "ubuntu"
    assert block["environment"]["DOTFILES_PACKAGE_SET"] == "homelab"
    assert "KUBECONFIG" not in block["environment"]
    checkout = next(task for task in block["block"] if "ansible.builtin.git" in task)
    assert checkout["ansible.builtin.git"]["force"] is False


@pytest.mark.parametrize("revision", ["main", "HEAD", "short-sha"])
def test_ansible_rejects_mutable_dotfiles_revisions_before_installing(tmp_path, revision):
    playbook = tmp_path / "invalid-pin.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "Validate the dotfiles revision guard without provisioning",
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": {"dotfiles_revision": revision},
                    "roles": ["dotfiles"],
                }
            ]
        )
    )
    environment = os.environ | {"ANSIBLE_STDOUT_CALLBACK": "ansible.posix.json"}
    result = subprocess.run(
        [
            "ansible-playbook",
            "-i",
            "localhost,",
            str(playbook),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=environment,
    )
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["stats"]["localhost"]["changed"] == 0
    assert report["stats"]["localhost"]["failures"] == 1
    assert len(report["plays"][0]["tasks"]) == 1


def test_ansible_dotfiles_configuration_converges_without_hiding_changes(tmp_path):
    home = tmp_path / "home"
    checkout = tmp_path / "checkout"
    home.mkdir()
    (checkout / "scripts").mkdir(parents=True)
    (checkout / "scripts/plugins.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'if [[ "$2" == check ]]; then [[ -f "$HOME/plugin-ready" ]] || exit 3; '
        'else printf ready > "$HOME/plugin-ready"; fi\n'
    )
    (checkout / "bootstrap.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'if [[ " $* " == *" --check "* ]]; then '
        '[[ -f "$HOME/config-ready" ]] && [[ "$(<"$HOME/config-ready")" == desired ]] || exit 3; '
        'else printf desired > "$HOME/config-ready"; fi\n'
    )
    playbook = tmp_path / "configuration.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "Exercise dotfiles role command contracts in a private fixture",
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "environment": {"HOME": str(home)},
                    "vars": {"dotfiles_checkout": str(checkout), "dotfiles_profile": "personal"},
                    "tasks": [
                        {
                            "name": "Run real role configuration tasks",
                            "ansible.builtin.include_role": {
                                "name": "dotfiles",
                                "tasks_from": "configure.yml",
                            },
                        }
                    ],
                }
            ]
        )
    )
    environment = os.environ | {"ANSIBLE_STDOUT_CALLBACK": "ansible.posix.json"}

    def configure():
        result = subprocess.run(
            [
                "ansible-playbook",
                "-i",
                "localhost,",
                str(playbook),
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=environment,
        )
        return json.loads(result.stdout)

    first = configure()
    assert first["stats"]["localhost"]["changed"] == 2
    homelab.validate_idempotence(configure(), {"localhost"})
    (home / "config-ready").write_text("drift")
    repaired = configure()
    assert repaired["stats"]["localhost"]["changed"] == 1
    assert (home / "config-ready").read_text() == "desired"


@pytest.mark.parametrize(
    "defect", ["missing-worker", "duplicate-ip", "duplicate-mac", "wrong-user", "wrong-name"]
)
def test_invalid_inventory_is_rejected(inventory, defect):
    agents = inventory["all"]["children"]["k3s_cluster"]["children"]["k3s_agents"]["hosts"]
    if defect == "missing-worker":
        agents.pop("pn51-worker-3")
    elif defect == "duplicate-ip":
        agents["pn51-worker-2"]["ansible_host"] = agents["pn51-worker-1"]["ansible_host"]
    elif defect == "duplicate-mac":
        agents["pn51-worker-2"]["libvirt_mac"] = agents["pn51-worker-1"]["libvirt_mac"]
    elif defect == "wrong-name":
        agents["pn51-worker-2"]["libvirt_name"] = "unmanaged-vm"
    else:
        inventory["all"]["vars"]["ansible_user"] = "root"
    with pytest.raises(ValueError):
        homelab.validate_inventory(inventory)


def test_private_writes_are_atomic_and_restrictive(tmp_path):
    target = tmp_path / "private" / "inventory.json"
    homelab.private_write(target, "first")
    homelab.private_write(target, "second")
    assert target.read_text() == "second"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert list(target.parent.iterdir()) == [target]


@pytest.mark.parametrize("dangling", [False, True])
def test_private_writes_refuse_symlinks_before_resolving(tmp_path, dangling):
    destination = tmp_path / "destination"
    if not dangling:
        destination.write_text("untouched")
    target = tmp_path / "symlink"
    target.symlink_to(destination)
    with pytest.raises(ValueError, match="symlink"):
        homelab.private_write(target, "secret")
    if dangling:
        assert not destination.exists()
    else:
        assert destination.read_text() == "untouched"


def test_private_writes_refuse_linked_directories(tmp_path):
    destination = tmp_path / "external"
    destination.mkdir()
    linked = tmp_path / "private"
    linked.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        homelab.private_write(linked / "vault.yml", "secret")
    assert list(destination.iterdir()) == []


def test_vault_generation_never_writes_plaintext(tmp_path, monkeypatch, capsys):
    observed = {}

    def encrypt(command, *, capture=False, stdin=None):
        assert command == ["ansible-vault", "encrypt", "--output", "-"]
        assert capture
        observed.update(json.loads(stdin))
        return "$ANSIBLE_VAULT;1.1;AES256\nencrypted-test-payload\n"

    monkeypatch.setattr(homelab, "execute", encrypt)
    target = tmp_path / "private" / "vault.yml"
    homelab.create_vault(target)
    assert re.fullmatch(r"[a-f0-9]{64}", observed["k3s_token"])
    assert len(observed["grafana_admin_password"]) >= 24
    assert observed["authelia_password_hash"].startswith("$argon2id$")
    assert homelab.PasswordHasher().verify(
        observed["authelia_password_hash"], observed["authelia_password"]
    )
    assert target.read_text().startswith("$ANSIBLE_VAULT;")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    output = capsys.readouterr()
    assert observed["k3s_token"] not in output.out + output.err + target.read_text()
    assert observed["grafana_admin_password"] not in output.out + output.err + target.read_text()
    with pytest.raises(ValueError, match="already exists"):
        homelab.create_vault(target)


def test_internal_pki_is_private_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(homelab, "LOCAL", tmp_path)
    homelab.create_pki("pn51.example.test")
    source = tmp_path / "pki/tls.crt"
    original = source.read_bytes()
    certificate = x509.load_pem_x509_certificate(original)
    names = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "*.pn51.example.test" in names.get_values_for_type(x509.DNSName)
    homelab.create_pki("pn51.example.test")
    assert source.read_bytes() == original
    assert stat.S_IMODE((tmp_path / "pki/ca.key").stat().st_mode) == 0o600
    with pytest.raises(ValueError, match="another domain"):
        homelab.create_pki("another.example.test")


def test_cloudinit_iso_uses_real_joliet_seed_files(tmp_path):
    for name in ("user-data", "meta-data", "network-config"):
        (tmp_path / name).write_text(f"{name}\n")
    target = tmp_path / "seed.iso"
    subprocess.run(
        [
            homelab.sys.executable,
            str(ROOT / "scripts/mkisofs"),
            "-output",
            str(target),
            "-volid",
            "cidata",
            "-joliet",
            "-rock",
            *[str(tmp_path / name) for name in ("user-data", "meta-data", "network-config")],
        ],
        check=True,
    )
    image = pycdlib.PyCdlib()
    image.open(str(target))
    try:
        output = io.BytesIO()
        image.get_file_from_iso_fp(output, joliet_path="/network-config")
        assert output.getvalue() == b"network-config\n"
        for name, identifier in {
            "user-data": "USER_DAT",
            "meta-data": "META_DAT",
            "network-config": "NETWORK_",
        }.items():
            primary = io.BytesIO()
            image.get_file_from_iso_fp(primary, iso_path=f"/{identifier}.;1")
            assert primary.getvalue() == f"{name}\n".encode()
        assert image.pvd.volume_identifier.decode().strip() == "cidata"
    finally:
        image.close()


def test_vault_encryption_failure_leaves_no_output(tmp_path, monkeypatch):
    def fail(command, **kwargs):
        raise subprocess.CalledProcessError(7, command)

    monkeypatch.setattr(homelab, "execute", fail)
    target = tmp_path / "vault.yml"
    with pytest.raises(subprocess.CalledProcessError):
        homelab.create_vault(target)
    assert not target.exists()


def test_idempotence_requires_all_hosts():
    homelab.validate_idempotence({"stats": {"node": {"ok": 10, "changed": 0}}}, {"node"})
    with pytest.raises(ValueError, match="every expected"):
        homelab.validate_idempotence({"stats": {"node": {"changed": 0}}}, {"node", "missing"})
    with pytest.raises(ValueError):
        homelab.validate_idempotence({"stats": {}})


@pytest.mark.parametrize("counter", ["changed", "failures", "unreachable", "rescued", "ignored"])
def test_idempotence_rejects_changes_and_hidden_failures(counter):
    with pytest.raises(ValueError, match="not clean"):
        homelab.validate_idempotence({"stats": {"node": {counter: 1}}})


def test_local_volume_replacement_guard():
    volume = {
        "metadata": {"name": "prometheus-data"},
        "spec": {
            "hostPath": {"path": "/var/lib/rancher/k3s/storage/data"},
            "nodeAffinity": {
                "required": {
                    "nodeSelectorTerms": [
                        {
                            "matchExpressions": [
                                {
                                    "key": "kubernetes.io/hostname",
                                    "operator": "In",
                                    "values": ["pn51-worker-1"],
                                }
                            ]
                        }
                    ]
                }
            },
        },
    }
    assert homelab.local_volumes_for_node([volume], "pn51-worker-1") == ["prometheus-data"]
    assert homelab.local_volumes_for_node([volume], "pn51-worker-2") == []
    volume["spec"]["hostPath"]["path"] = "/srv/homelab-data/storage/prometheus"
    assert homelab.local_volumes_for_node([volume], "pn51-worker-1") == []
    volume["spec"]["hostPath"]["path"] = "/srv/homelab-data/storage/../../unprotected"
    assert homelab.local_volumes_for_node([volume], "pn51-worker-1") == ["prometheus-data"]
    assert (
        homelab.local_volumes_for_node(
            [
                {"metadata": {"name": "nfs-data"}, "spec": {"nfs": {"server": "192.0.2.1"}}},
            ],
            "pn51-worker-1",
        )
        == []
    )
    del volume["spec"]["nodeAffinity"]
    assert homelab.local_volumes_for_node([volume], "pn51-worker-2") == ["prometheus-data"]


def test_replacement_plan_cannot_expand_scope():
    resource = {
        "address": 'libvirt_domain.node["pn51-worker-1"]',
        "change": {"actions": ["delete", "create"]},
    }
    disk = copy.deepcopy(resource)
    disk["address"] = 'libvirt_volume.node["pn51-worker-1"]'
    homelab.validate_replacement_plan({"resource_changes": [resource, disk]}, "pn51-worker-1")
    forbidden = copy.deepcopy(resource)
    forbidden["address"] = 'libvirt_domain.node["pn51-server-1"]'
    with pytest.raises(ValueError, match="outside"):
        homelab.validate_replacement_plan(
            {"resource_changes": [resource, disk, forbidden]}, "pn51-worker-1"
        )
    with pytest.raises(ValueError, match="root disk"):
        homelab.validate_replacement_plan({"resource_changes": [resource]}, "pn51-worker-1")
    with pytest.raises(ValueError, match="explicit replacement"):
        homelab.validate_replacement_plan({"resource_changes": []}, "pn51-worker-1")


def test_control_plane_replacement_is_refused_before_any_command(inventory, tmp_path, monkeypatch):
    (tmp_path / "inventory.json").write_text(json.dumps(inventory))
    monkeypatch.setattr(homelab, "LOCAL", tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("Control-plane replacement must not execute a command")

    monkeypatch.setattr(homelab, "execute", forbidden)
    with pytest.raises(ValueError, match="control-plane replacement"):
        homelab.replace_worker("pn51-server-1")


def test_wrong_worker_confirmation_is_refused_before_any_command(inventory, tmp_path, monkeypatch):
    (tmp_path / "inventory.json").write_text(json.dumps(inventory))
    monkeypatch.setattr(homelab, "LOCAL", tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("Wrong confirmation must not execute a command")

    monkeypatch.setattr(homelab, "execute", forbidden)
    with pytest.raises(ValueError, match="exactly match"):
        homelab.replace_worker("pn51-worker-2", confirmation="replace pn51-worker-1")


def test_confirmed_worker_replacement_still_validates_scope(inventory, tmp_path, monkeypatch):
    (tmp_path / "inventory.json").write_text(json.dumps(inventory))
    monkeypatch.setattr(homelab, "LOCAL", tmp_path)
    nodes = [
        {
            "metadata": {"name": name},
            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
        }
        for name in homelab.validate_inventory(inventory)
    ]
    forbidden_change = {
        "address": 'libvirt_domain.node["pn51-server-1"]',
        "change": {"actions": ["delete", "create"]},
    }
    responses = iter(
        [
            json.dumps({"items": nodes}),
            json.dumps({"items": []}),
            "",
            json.dumps({"resource_changes": [forbidden_change]}),
        ]
    )

    def execute(command, **kwargs):
        assert "drain" not in command and "apply" not in command
        return next(responses)

    monkeypatch.setattr(homelab, "execute", execute)
    with pytest.raises(ValueError, match="outside"):
        homelab.replace_worker("pn51-worker-2", confirmation="replace pn51-worker-2")


def test_ansible_does_not_override_inventory_networks(inventory, tmp_path):
    inventory["all"]["vars"].update(
        {
            "k3s_pod_cidr": "172.20.0.0/16",
            "k3s_service_cidr": "172.21.0.0/16",
            "k3s_cluster_dns": "172.21.0.10",
        }
    )
    source = tmp_path / "inventory.json"
    source.write_text(json.dumps(inventory))
    result = subprocess.run(
        [
            "ansible-inventory",
            "--playbook-dir",
            str(ROOT / "pn51/ansible"),
            "--inventory",
            str(source),
            "--host",
            "pn51-server-1",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    resolved = json.loads(result.stdout)
    for key in ("k3s_pod_cidr", "k3s_service_cidr", "k3s_cluster_dns"):
        assert resolved[key] == inventory["all"]["vars"][key]


@pytest.mark.parametrize("kind", ["Deployment", "StatefulSet", "DaemonSet"])
def test_workload_readiness_rejects_zero_and_partial_replicas(kind):
    item = {"kind": kind, "spec": {"replicas": 2}, "status": {}}
    assert not homelab.workload_ready(item)
    if kind == "DaemonSet":
        item["status"] = {"desiredNumberScheduled": 2, "numberReady": 1}
    else:
        item["status"] = {"readyReplicas": 1}
    assert not homelab.workload_ready(item)
    if kind == "DaemonSet":
        item["status"]["numberReady"] = 2
    else:
        item["status"]["readyReplicas"] = 2
    assert homelab.workload_ready(item)


@pytest.mark.parametrize(
    "defect",
    [
        "anonymous-dashboard",
        "missing-tls",
        "root-pod",
        "cluster-admin",
        "persistent-token",
        "bad-entrypoint",
        "service-links",
        "homepage-token",
        "homepage-hosts",
    ],
)
def test_platform_security_rejects_unsafe_declarations(defect):
    source = homelab.LOCAL / "test-templates/platform-resources.yml"
    if not source.exists():
        pytest.skip("Run make platform-check to render the real platform manifest")
    documents = homelab.parse_yaml_documents(source.read_text())
    homelab.validate_platform(documents)
    if defect in {"anonymous-dashboard", "missing-tls"}:
        ingress = next(
            item
            for item in documents
            if item["kind"] == "Ingress" and item["metadata"]["name"] == "grafana"
        )
        if defect == "anonymous-dashboard":
            ingress["metadata"]["annotations"].pop(
                "traefik.ingress.kubernetes.io/router.middlewares"
            )
        else:
            ingress["spec"].pop("tls")
    elif defect == "root-pod":
        deployment = next(item for item in documents if item["kind"] == "Deployment")
        deployment["spec"]["template"]["spec"]["securityContext"]["runAsNonRoot"] = False
    elif defect == "cluster-admin":
        binding = next(item for item in documents if item["kind"] == "ClusterRoleBinding")
        binding["roleRef"]["name"] = "cluster-admin"
    elif defect in {"bad-entrypoint", "service-links"}:
        deployment = next(
            item
            for item in documents
            if item["kind"] == "Deployment" and item["metadata"]["name"] == "authelia"
        )
        pod = deployment["spec"]["template"]["spec"]
        if defect == "bad-entrypoint":
            pod["containers"][0]["args"] = ["--config=/config/configuration.yml"]
        else:
            pod["enableServiceLinks"] = True
    elif defect in {"homepage-token", "homepage-hosts"}:
        deployment = next(
            item
            for item in documents
            if item["kind"] == "Deployment" and item["metadata"]["name"] == "homepage"
        )
        pod = deployment["spec"]["template"]["spec"]
        if defect == "homepage-token":
            pod["automountServiceAccountToken"] = True
        else:
            pod["containers"][0]["env"] = [{"name": "HOMEPAGE_ALLOWED_HOSTS", "value": "*"}]
    else:
        documents.append(
            {"apiVersion": "v1", "kind": "Secret", "type": "kubernetes.io/service-account-token"}
        )
    with pytest.raises(ValueError):
        homelab.validate_platform(documents)


@pytest.mark.parametrize(
    "defect", ["default-open", "outside-repository", "outside-namespace", "cluster-resources"]
)
def test_argocd_project_scope_rejects_infrastructure_adoption(defect):
    source = homelab.LOCAL / "test-templates/argocd-projects.yml"
    if not source.exists():
        pytest.skip("Run make argocd-chart-check to render the real project boundary")
    projects = homelab.parse_yaml_documents(source.read_text())
    settings = homelab.load_settings()
    homelab.validate_argocd_projects(projects, settings)
    by_name = {item["metadata"]["name"]: item["spec"] for item in projects}
    if defect == "default-open":
        by_name["default"]["sourceRepos"] = ["*"]
    elif defect == "outside-repository":
        by_name["homelab"]["sourceRepos"] = ["*"]
    elif defect == "outside-namespace":
        by_name["homelab"]["destinations"][0]["namespace"] = "kube-system"
    else:
        by_name["homelab"]["clusterResourceWhitelist"] = [{"group": "*", "kind": "*"}]
    with pytest.raises(ValueError):
        homelab.validate_argocd_projects(projects, settings)


def test_public_files_exclude_private_artifacts():
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    files = set(result.stdout.split("\0")) - {""}
    for name in files:
        source = Path(name)
        assert not name.startswith((".local/", ".secrets/", "private-keys/", ".gstack/")), name
        assert not source.name.endswith((".tfvars", ".tfvars.json", ".tfstate", ".tfplan")), name
        assert ".tfstate." not in source.name, name
        path = ROOT / source
        if path.is_file() and path.suffix in {".yml", ".yaml", ".md", ".tf", ".py", ".sh"}:
            assert not re.search(
                r"^-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----$",
                path.read_text(),
                re.MULTILINE,
            ), name


def test_pinned_chart_integration_when_downloaded():
    settings = homelab.load_settings()
    archive = homelab.LOCAL / f"kube-prometheus-stack-{settings['monitoring_chart_version']}.tgz"
    if not archive.exists():
        pytest.skip("Run the required chart-check gate to download the pinned chart")
    homelab.check_chart()
