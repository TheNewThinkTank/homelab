variable "libvirt_uri" {
  description = "System libvirt on the Ubuntu PN51, reached using the existing SSH identity."
  type        = string
  default     = "qemu+ssh://gus@pn51/system"

  validation {
    condition     = can(regex("^qemu\\+ssh://[^/]+/system", var.libvirt_uri))
    error_message = "Use SSH to the PN51 system libvirt, never the Mac or a session hypervisor."
  }
}

variable "host_ssh_alias" {
  description = "Existing, host-key-verified SSH alias used as the guest jump host."
  type        = string
  default     = "pn51"

  validation {
    condition     = can(regex("^[a-zA-Z0-9][a-zA-Z0-9_.-]*$", var.host_ssh_alias))
    error_message = "Use a plain SSH hostname or alias, not shell arguments."
  }
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

variable "network_cidr" {
  description = "Dedicated libvirt NAT subnet; must not overlap LAN, pods, or services."
  type        = string
  default     = "10.51.0.0/24"

  validation {
    condition     = can(cidrnetmask(var.network_cidr)) && try(cidrhost(var.network_cidr, 0) == split("/", var.network_cidr)[0] && split("/", var.network_cidr)[1] == "24", false)
    error_message = "Use a canonical IPv4 /24 subnet."
  }
}

variable "gateway" {
  description = "Libvirt's NAT gateway address within network_cidr."
  type        = string
  default     = "10.51.0.1"

  validation {
    condition = try(
      var.gateway == cidrhost(var.network_cidr, 1),
      false
    )
    error_message = "The libvirt NAT gateway must be the subnet's first usable address."
  }
}

variable "node_ip_offset" {
  description = "First node host offset within network_cidr; four consecutive addresses are used."
  type        = number
  default     = 40

  validation {
    condition = try(
      floor(var.node_ip_offset) == var.node_ip_offset && var.node_ip_offset > 1 &&
      var.node_ip_offset + 3 < 255,
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

variable "ssh_public_keys" {
  description = "Existing public SSH keys only. Private keys and passwords never enter Terraform."
  type        = list(string)

  validation {
    condition     = length(var.ssh_public_keys) > 0 && alltrue([for key in var.ssh_public_keys : can(regex("^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp[0-9]+) [A-Za-z0-9+/=]+( .*)?$", trimspace(key)))])
    error_message = "Supply at least one OpenSSH public key, not a private key or file path."
  }
}

variable "vm_memory_mb" {
  description = "Fixed RAM per server VM; four 4 GiB guests leave about 15 GiB for Ubuntu Desktop."
  type        = number
  default     = 4096

  validation {
    condition     = floor(var.vm_memory_mb) == var.vm_memory_mb && var.vm_memory_mb >= 4096 && var.vm_memory_mb <= 6144
    error_message = "Use 4096-6144 MiB per VM, retaining at least 6 GiB for the Desktop host."
  }
}

variable "vm_vcpus" {
  description = "Virtual CPUs per guest on the 16-thread Ryzen host."
  type        = number
  default     = 2

  validation {
    condition     = floor(var.vm_vcpus) == var.vm_vcpus && var.vm_vcpus >= 2 && var.vm_vcpus <= 4
    error_message = "Use two to four vCPUs per guest."
  }
}

variable "vm_disk_gb" {
  description = "Sparse qcow2 root disk per VM; includes node-local persistent volumes."
  type        = number
  default     = 64

  validation {
    condition     = floor(var.vm_disk_gb) == var.vm_disk_gb && var.vm_disk_gb >= 32
    error_message = "Allocate an integer disk size of at least 32 GiB per server VM."
  }
}

variable "vm_data_disk_gb" {
  description = "Protected per-node data disk; never destroyed by worker root replacement."
  type        = number
  default     = 64

  validation {
    condition     = floor(var.vm_data_disk_gb) == var.vm_data_disk_gb && var.vm_data_disk_gb >= 32
    error_message = "Allocate at least 32 GiB per protected data disk."
  }
}

variable "image_path" {
  description = "Optional local image path; defaults to make image's private, pinned download."
  type        = string
  default     = null
}

variable "image_checksum" {
  description = "Optional reviewed SHA-256 override; defaults to the pinned image manifest."
  type        = string
  default     = null

  validation {
    condition     = var.image_checksum == null || can(regex("^[a-f0-9]{64}$", var.image_checksum))
    error_message = "Use a SHA-256 hex digest."
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
