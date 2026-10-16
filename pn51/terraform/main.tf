locals {
  ubuntu_image_url    = "https://cloud-images.ubuntu.com/releases/resolute/release-20260927/ubuntu-26.04-server-cloudimg-amd64.img"
  ubuntu_image_sha256 = "8800651811af9a85465ad1d552add729947bb16488dddb4a9b5305a3d97332b2"
  nodes = {
    for index in range(4) : "${var.cluster_name}-${index == 0 ? "server-1" : "worker-${index}"}" => {
      vm_id   = var.vm_id_start + index
      address = cidrhost(var.network_cidr, var.node_ip_offset + index)
      role    = index == 0 ? "server" : "agent"
    }
  }
  node_addresses = join(",", [for node in values(local.nodes) : "${node.address}/32"])
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

resource "proxmox_download_file" "ubuntu" {
  node_name           = var.proxmox_node
  datastore_id        = var.image_datastore
  content_type        = "import"
  file_name           = "ubuntu-26.04-amd64-20260927.qcow2"
  url                 = local.ubuntu_image_url
  checksum            = local.ubuntu_image_sha256
  checksum_algorithm  = "sha256"
  verify              = true
  overwrite           = false
  overwrite_unmanaged = false
}

resource "proxmox_virtual_environment_vm" "node" {
  for_each = local.nodes

  node_name       = var.proxmox_node
  vm_id           = each.value.vm_id
  name            = each.key
  description     = "Terraform-managed Ubuntu 26.04 Desktop / K3s ${each.value.role}"
  tags            = ["terraform", "ubuntu-26-04", "k3s", each.value.role]
  on_boot         = true
  started         = true
  stop_on_destroy = true
  scsi_hardware   = "virtio-scsi-single"
  boot_order      = ["scsi0"]

  cpu {
    cores = 2
    type  = "host"
  }

  memory {
    dedicated = var.vm_memory_mb
    floating  = 0
  }

  agent {
    enabled = true
    trim    = true
    wait_for_ip {
      disabled = true
    }
  }

  disk {
    datastore_id = var.vm_datastore
    import_from  = proxmox_download_file.ubuntu.id
    interface    = "scsi0"
    file_format  = "raw"
    size         = var.vm_disk_gb
    discard      = "on"
    iothread     = true
  }

  initialization {
    datastore_id = var.vm_datastore
    dns {
      servers = var.dns_servers
    }
    ip_config {
      ipv4 {
        address = "${each.value.address}/${split("/", var.network_cidr)[1]}"
        gateway = var.gateway
      }
    }
    user_account {
      username = "ubuntu"
      keys     = [for key in var.ssh_public_keys : trimspace(key)]
    }
  }

  network_device {
    bridge   = var.bridge
    model    = "virtio"
    firewall = true
  }

  operating_system {
    type = "l26"
  }

  vga {
    type   = "std"
    memory = 32
  }

  serial_device {}

  startup {
    order    = each.value.role == "server" ? 1 : 2
    up_delay = 30
  }
}

resource "proxmox_virtual_environment_firewall_rules" "node" {
  for_each = local.nodes

  node_name = var.proxmox_node
  vm_id     = proxmox_virtual_environment_vm.node[each.key].vm_id

  dynamic "rule" {
    for_each = var.admin_cidrs
    content {
      type    = "in"
      action  = "ACCEPT"
      proto   = "tcp"
      dport   = each.value.role == "server" ? "22,6443" : "22"
      source  = rule.value
      comment = "Trusted administrators only"
    }
  }

  rule {
    type    = "in"
    action  = "ACCEPT"
    proto   = "udp"
    dport   = "8472"
    source  = local.node_addresses
    comment = "Flannel VXLAN between cluster nodes only"
  }

  rule {
    type    = "in"
    action  = "ACCEPT"
    proto   = "tcp"
    dport   = each.value.role == "server" ? "6443,10250" : "10250"
    source  = local.node_addresses
    comment = "Kubernetes API and kubelet between cluster nodes only"
  }

  rule {
    type    = "in"
    action  = "ACCEPT"
    proto   = "icmp"
    source  = local.node_addresses
    comment = "Cluster network diagnostics"
  }
}

resource "proxmox_virtual_environment_firewall_options" "node" {
  for_each   = local.nodes
  depends_on = [proxmox_virtual_environment_firewall_rules.node]

  node_name     = var.proxmox_node
  vm_id         = proxmox_virtual_environment_vm.node[each.key].vm_id
  enabled       = true
  input_policy  = "DROP"
  output_policy = "ACCEPT"
  ipfilter      = false
  macfilter     = true
  dhcp          = false
  ndp           = false
  radv          = false
}
