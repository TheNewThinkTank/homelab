mock_provider "libvirt" {
  mock_resource "libvirt_volume" {
    defaults = {
      id = "test-volume"
    }
  }
}

variables {
  ssh_public_keys = ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestOnlyNotAnActualPrivateKey"]
  image_path      = "../../LICENSE"
  image_checksum  = filesha256("../../LICENSE")
}

run "four_server_vms" {
  command = plan

  assert {
    condition     = length(libvirt_domain.node) == 4 && length(libvirt_volume.node) == 4 && length(libvirt_cloudinit_disk.node) == 4
    error_message = "Provision exactly four VMs with independent disks and cloud-init seeds."
  }
  assert {
    condition     = length([for node in values(local.nodes) : node if node.role == "server"]) == 1 && length([for node in values(local.nodes) : node if node.role == "agent"]) == 3
    error_message = "The cluster must contain one server and three agents."
  }
  assert {
    condition     = sum([for vm in values(libvirt_domain.node) : vm.memory]) == 16384
    error_message = "Default VM RAM must leave about half the host RAM for Ubuntu Desktop."
  }
  assert {
    condition     = alltrue([for vm in values(libvirt_domain.node) : vm.qemu_agent && !vm.network_interface[0].wait_for_lease])
    error_message = "VMs need guest-agent channels without a bootstrap readiness deadlock."
  }
  assert {
    condition     = alltrue([for vm in values(libvirt_domain.node) : vm.autostart && vm.running])
    error_message = "All guests must start automatically at boot."
  }
  assert {
    condition     = libvirt_network.cluster.mode == "nat" && libvirt_network.cluster.autostart
    error_message = "Use an isolated NAT network without changing the Wi-Fi host interface."
  }
  assert {
    condition     = alltrue([for disk in values(libvirt_volume.node) : disk.size == 64 * 1024 * 1024 * 1024 && disk.format == "qcow2"])
    error_message = "Each VM must have an independently replaceable sparse 64 GiB root disk."
  }
  assert {
    condition     = length(libvirt_volume.data) == 4 && alltrue([for vm in values(libvirt_domain.node) : length(vm.disk) == 2])
    error_message = "Each VM must attach a separate, protected persistent data disk."
  }
  assert {
    condition     = length(output.ansible_inventory.all.children.k3s_cluster.children.k3s_server.hosts) == 1 && length(output.ansible_inventory.all.children.k3s_cluster.children.k3s_agents.hosts) == 3
    error_message = "Terraform must produce a directly usable Ansible inventory."
  }
  assert {
    condition     = output.nodes["pn51-server-1"].address == "10.51.0.40" && output.nodes["pn51-worker-3"].mac == "52:54:00:51:00:2b"
    error_message = "VM names, MACs, and addresses must be deterministic."
  }
  assert {
    condition     = alltrue([for seed in values(libvirt_cloudinit_disk.node) : !yamldecode(seed.user_data).ssh_pwauth && yamldecode(seed.user_data).disable_root])
    error_message = "Cloud-init must disable password and root SSH."
  }
  assert {
    condition     = alltrue([for name, seed in libvirt_cloudinit_disk.node : yamldecode(seed.network_config).ethernets.eth0.addresses == ["${local.nodes[name].address}/24"]])
    error_message = "Cloud-init must own every declared static IPv4 address."
  }
  assert {
    condition     = alltrue([for name, seed in libvirt_cloudinit_disk.node : !contains(keys(yamldecode(seed.network_config).ethernets.eth0), "set-name") && yamldecode(seed.network_config).ethernets.eth0.match.macaddress == local.nodes[name].mac])
    error_message = "Match guest NICs by MAC without racing to rename active interfaces."
  }
}

run "reject_host_memory_exhaustion" {
  command = plan
  variables {
    vm_memory_mb = 8192
  }
  expect_failures = [var.vm_memory_mb]
}

run "reject_small_guest_memory" {
  command = plan
  variables {
    vm_memory_mb = 2048
  }
  expect_failures = [var.vm_memory_mb]
}

run "reject_gateway_collision" {
  command = plan
  variables {
    node_ip_offset = 1
  }
  expect_failures = [var.node_ip_offset]
}

run "reject_gateway_outside_network" {
  command = plan
  variables {
    gateway = "192.168.99.1"
  }
  expect_failures = [var.gateway]
}

run "reject_node_address_overflow" {
  command = plan
  variables {
    node_ip_offset = 252
  }
  expect_failures = [var.node_ip_offset]
}

run "reject_overlapping_pod_network" {
  command = plan
  variables {
    pod_cidr = "10.51.0.0/16"
  }
  expect_failures = [output.ansible_inventory]
}

run "reject_overlapping_service_network" {
  command = plan
  variables {
    service_cidr = "10.51.0.0/24"
  }
  expect_failures = [output.ansible_inventory]
}

run "reject_private_key_input" {
  command = plan
  variables {
    ssh_public_keys = ["-----BEGIN OPENSSH PRIVATE KEY-----"]
  }
  expect_failures = [var.ssh_public_keys]
}

run "reject_wrong_image_digest" {
  command = plan
  variables {
    image_checksum = "0000000000000000000000000000000000000000000000000000000000000000"
  }
  expect_failures = [libvirt_volume.ubuntu]
}
