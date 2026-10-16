terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.116.1"
    }
  }
}

provider "proxmox" {
  insecure = false
}
