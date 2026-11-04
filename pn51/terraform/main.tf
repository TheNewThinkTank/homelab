locals {
  image          = jsondecode(file("${path.module}/image.json"))
  image_path     = abspath(coalesce(var.image_path, "${path.module}/../../.local/images/${local.image.name}"))
  image_checksum = coalesce(var.image_checksum, local.image.sha256)
  nodes = {
    for index in range(4) : "${var.cluster_name}-${index == 0 ? "server-1" : "worker-${index}"}" => {
      address = cidrhost(var.network_cidr, var.node_ip_offset + index)
      mac     = "52:54:00:51:00:${format("%02x", var.node_ip_offset + index)}"
      role    = index == 0 ? "server" : "agent"
    }
  }
  networks = {
    nodes    = var.network_cidr
    pods     = var.pod_cidr
    services = var.service_cidr
  }
  networks_disjoint = alltrue(flatten([
    for name, network in local.networks : [
      for other_name, other_network in local.networks :
      cidrhost("${cidrhost(network, 0)}/${split("/", other_network)[1]}", 0) != cidrhost(other_network, 0)
      if name != other_name
    ]
  ]))
}

resource "libvirt_pool" "cluster" {
  name = var.cluster_name
  type = "dir"
  target {
    path = "/var/lib/libvirt/homelab/${var.cluster_name}"
  }
}

resource "libvirt_network" "cluster" {
  name      = var.cluster_name
  mode      = "nat"
  bridge    = "virbr51"
  domain    = "${var.cluster_name}.internal"
  addresses = [var.network_cidr]
  autostart = true
  dhcp {
    enabled = true
  }
  dns {
    enabled = true
  }
}

resource "libvirt_volume" "ubuntu" {
  name   = local.image.name
  pool   = libvirt_pool.cluster.name
  source = local.image_path
  format = "qcow2"

  lifecycle {
    precondition {
      condition     = try(filesha256(local.image_path), "") == local.image_checksum
      error_message = "Download the pinned, checksummed Ubuntu image with make image before planning."
    }
  }
}

resource "libvirt_volume" "node" {
  for_each = local.nodes

  name           = "${each.key}.qcow2"
  pool           = libvirt_pool.cluster.name
  base_volume_id = libvirt_volume.ubuntu.id
  format         = "qcow2"
  size           = var.vm_disk_gb * 1024 * 1024 * 1024
}

resource "libvirt_volume" "data" {
  for_each = local.nodes

  name   = "${each.key}-data.qcow2"
  pool   = libvirt_pool.cluster.name
  format = "qcow2"
  size   = var.vm_data_disk_gb * 1024 * 1024 * 1024

  lifecycle {
    prevent_destroy = true
  }
}

resource "libvirt_cloudinit_disk" "node" {
  for_each = local.nodes

  name = "${each.key}-seed.iso"
  pool = libvirt_pool.cluster.name
  meta_data = yamlencode({
    "instance-id"    = each.key
    "local-hostname" = each.key
  })
  user_data = "#cloud-config\n${yamlencode({
    hostname         = each.key
    manage_etc_hosts = true
    ssh_pwauth       = false
    disable_root     = true
    ssh_deletekeys   = true
    users = [{
      name                = "ubuntu"
      groups              = ["adm", "sudo"]
      shell               = "/bin/bash"
      lock_passwd         = true
      sudo                = "ALL=(ALL) NOPASSWD:ALL"
      ssh_authorized_keys = [for key in var.ssh_public_keys : trimspace(key)]
    }]
    packages = ["qemu-guest-agent"]
    runcmd   = [["systemctl", "enable", "--now", "qemu-guest-agent"]]
  })}"
  network_config = yamlencode({
    version = 2
    ethernets = {
      eth0 = {
        match       = { macaddress = each.value.mac }
        dhcp4       = false
        dhcp6       = false
        addresses   = ["${each.value.address}/${split("/", var.network_cidr)[1]}"]
        routes      = [{ to = "default", via = var.gateway }]
        nameservers = { addresses = var.dns_servers }
      }
    }
  })
}

resource "libvirt_domain" "node" {
  for_each = local.nodes

  name       = each.key
  memory     = var.vm_memory_mb
  vcpu       = var.vm_vcpus
  autostart  = true
  running    = true
  qemu_agent = true
  cloudinit  = libvirt_cloudinit_disk.node[each.key].id

  xml {
    xslt = templatefile("${path.module}/domain.xslt", {
      base_image_path = "/var/lib/libvirt/homelab/${var.cluster_name}/${local.image.name}"
      root_disk_path  = libvirt_volume.node[each.key].id
      data_disk_path  = libvirt_volume.data[each.key].id
    })
  }

  cpu {
    mode = "host-passthrough"
  }
  disk {
    volume_id = libvirt_volume.node[each.key].id
  }
  disk {
    volume_id = libvirt_volume.data[each.key].id
  }
  network_interface {
    network_id     = libvirt_network.cluster.id
    hostname       = each.key
    mac            = each.value.mac
    wait_for_lease = false
  }
  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }
}
