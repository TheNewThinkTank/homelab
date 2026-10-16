mock_provider "proxmox" {
  mock_resource "proxmox_download_file" {
    defaults = {
      id = "local:import/ubuntu-26.04-amd64-20260927.qcow2"
    }
  }
}

variables {
  proxmox_node    = "pn51"
  network_cidr    = "192.168.50.0/24"
  gateway         = "192.168.50.1"
  admin_cidrs     = ["192.168.50.10/32"]
  ssh_public_keys = ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestOnlyNotAnActualPrivateKey"]
}

run "four_desktop_vms" {
  command = plan

  assert {
    condition     = length(proxmox_virtual_environment_vm.node) == 4
    error_message = "Provision exactly four VMs."
  }
  assert {
    condition     = length([for node in values(local.nodes) : node if node.role == "server"]) == 1 && length([for node in values(local.nodes) : node if node.role == "agent"]) == 3
    error_message = "The cluster must contain one server and three agents."
  }
  assert {
    condition     = sum([for vm in values(proxmox_virtual_environment_vm.node) : vm.memory[0].dedicated]) == 24576
    error_message = "Default VM RAM must leave 8 GiB for the 32 GiB PN51 host."
  }
  assert {
    condition     = alltrue([for vm in values(proxmox_virtual_environment_vm.node) : vm.agent[0].wait_for_ip[0].disabled && vm.network_device[0].firewall && vm.vga[0].type == "std"])
    error_message = "VMs need desktop displays, firewall enforcement, and no guest-agent bootstrap deadlock."
  }
  assert {
    condition     = alltrue([for vm in values(proxmox_virtual_environment_vm.node) : vm.disk[0].size >= 48 && vm.on_boot && vm.started])
    error_message = "Desktop disks must fit and all guests must start automatically."
  }
  assert {
    condition     = proxmox_download_file.ubuntu.checksum_algorithm == "sha256" && length(proxmox_download_file.ubuntu.checksum) == 64 && proxmox_download_file.ubuntu.verify && !proxmox_download_file.ubuntu.overwrite_unmanaged
    error_message = "The Ubuntu image must be checksummed, TLS-verified, and must not overwrite unmanaged images."
  }
  assert {
    condition     = alltrue([for options in values(proxmox_virtual_environment_firewall_options.node) : options.enabled && options.input_policy == "DROP"])
    error_message = "Each VM must default-deny ingress."
  }
  assert {
    condition     = length(output.ansible_inventory.all.children.k3s_cluster.children.k3s_server.hosts) == 1 && length(output.ansible_inventory.all.children.k3s_cluster.children.k3s_agents.hosts) == 3
    error_message = "Terraform must produce a directly usable Ansible inventory."
  }
  assert {
    condition     = output.nodes["pn51-server-1"].address == "192.168.50.40" && output.nodes["pn51-worker-3"].vm_id == 5103
    error_message = "VM names, IDs, and addresses must be deterministic."
  }
}

run "reject_world_open_administration" {
  command = plan
  variables {
    admin_cidrs = ["0.0.0.0/0"]
  }
  expect_failures = [var.admin_cidrs]
}

run "reject_small_desktop_memory" {
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
    pod_cidr = "192.168.0.0/16"
  }
  expect_failures = [output.ansible_inventory]
}

run "reject_overlapping_service_network" {
  command = plan
  variables {
    service_cidr = "10.42.1.0/24"
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
