variable "proxmox_node" {
  description = "Existing Proxmox VE 9 node name; Terraform never installs or erases the host."
  type        = string
}

variable "vm_datastore" {
  description = "Datastore supporting VM and cloud-init disks."
  type        = string
  default     = "local-lvm"
}

variable "image_datastore" {
  description = "File-backed datastore with the Import content type enabled."
  type        = string
  default     = "local"
}

variable "bridge" {
  description = "Existing bridge connected to the private node network."
  type        = string
  default     = "vmbr0"
}

variable "cluster_name" {
  description = "Stable prefix for VM and Kubernetes node names."
  type        = string
  default     = "pn51"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,30}[a-z0-9]$", var.cluster_name))
    error_message = "Use 2-32 lowercase DNS-safe characters."
  }
}

variable "vm_id_start" {
  description = "First of four consecutive VM IDs; reserve these IDs exclusively for this lab."
  type        = number
  default     = 5100

  validation {
    condition     = floor(var.vm_id_start) == var.vm_id_start && var.vm_id_start >= 100 && var.vm_id_start <= 999999996
    error_message = "The first VM ID must be an integer between 100 and 999999996."
  }
}

variable "network_cidr" {
  description = "Private IPv4 LAN/VLAN subnet; reserve the four node addresses outside DHCP."
  type        = string

  validation {
    condition     = can(cidrnetmask(var.network_cidr)) && try(cidrhost(var.network_cidr, 0) == split("/", var.network_cidr)[0], false)
    error_message = "Use a canonical IPv4 subnet, for example 192.168.50.0/24."
  }
}

variable "gateway" {
  description = "IPv4 gateway on network_cidr."
  type        = string

  validation {
    condition = try(
      cidrhost("${var.gateway}/${split("/", var.network_cidr)[1]}", 0) == cidrhost(var.network_cidr, 0) &&
      var.gateway != cidrhost(var.network_cidr, 0) && var.gateway != cidrhost(var.network_cidr, -1),
      false
    )
    error_message = "The gateway must be a usable IPv4 address in network_cidr."
  }
}

variable "node_ip_offset" {
  description = "First node host offset within network_cidr; four consecutive addresses are used."
  type        = number
  default     = 40

  validation {
    condition = try(
      floor(var.node_ip_offset) == var.node_ip_offset && var.node_ip_offset > 0 &&
      var.node_ip_offset + 3 < pow(2, 32 - tonumber(split("/", var.network_cidr)[1])) - 1 &&
      !contains([for index in range(4) : cidrhost(var.network_cidr, var.node_ip_offset + index)], var.gateway),
      false
    )
    error_message = "Four usable, non-gateway node addresses must fit inside network_cidr."
  }
}

variable "dns_servers" {
  description = "Reachable IPv4 DNS resolvers for the VMs."
  type        = list(string)
  default     = ["1.1.1.1", "9.9.9.9"]

  validation {
    condition     = length(var.dns_servers) > 0 && alltrue([for address in var.dns_servers : can(cidrnetmask("${address}/32"))])
    error_message = "Provide at least one IPv4 DNS resolver."
  }
}

variable "admin_cidrs" {
  description = "Trusted administrator IPv4 CIDRs allowed to reach SSH and the Kubernetes API."
  type        = set(string)

  validation {
    condition     = length(var.admin_cidrs) > 0 && alltrue([for cidr in var.admin_cidrs : can(cidrnetmask(cidr)) && try(tonumber(split("/", cidr)[1]) > 0, false)])
    error_message = "Provide explicit trusted IPv4 CIDRs; 0.0.0.0/0 is forbidden."
  }
}

variable "ssh_public_keys" {
  description = "Existing public SSH keys only. Private keys and passwords never enter Terraform."
  type        = list(string)

  validation {
    condition     = length(var.ssh_public_keys) > 0 && alltrue([for key in var.ssh_public_keys : can(regex("^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp[0-9]+) [A-Za-z0-9+/=]+( .*)?$", trimspace(key)))])
    error_message = "Supply at least one OpenSSH public key, not a private key or file path."
  }
}

variable "vm_memory_mb" {
  description = "Fixed RAM per desktop VM; 6144 MiB x 4 leaves 8 GiB of the PN51's 32 GiB for Proxmox."
  type        = number
  default     = 6144

  validation {
    condition     = floor(var.vm_memory_mb) == var.vm_memory_mb && var.vm_memory_mb >= 6144
    error_message = "Ubuntu 26.04 Desktop guests require at least 6144 MiB each."
  }
}

variable "vm_disk_gb" {
  description = "Root disk per VM, including Desktop, container images, and local persistent volumes."
  type        = number
  default     = 80

  validation {
    condition     = floor(var.vm_disk_gb) == var.vm_disk_gb && var.vm_disk_gb >= 48
    error_message = "Allocate an integer disk size of at least 48 GiB per desktop VM."
  }
}

variable "pod_cidr" {
  description = "K3s IPv4 pod subnet; do not change on an existing cluster."
  type        = string
  default     = "10.42.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.pod_cidr)) && try(tonumber(split("/", var.pod_cidr)[1]) <= 22, false)
    error_message = "Use an IPv4 pod subnet with space for at least four /24 node subnets."
  }
}

variable "service_cidr" {
  description = "K3s IPv4 service subnet; do not change on an existing cluster."
  type        = string
  default     = "10.43.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.service_cidr)) && try(tonumber(split("/", var.service_cidr)[1]) <= 24, false)
    error_message = "Use an IPv4 service subnet with a prefix length of at most 24."
  }
}
