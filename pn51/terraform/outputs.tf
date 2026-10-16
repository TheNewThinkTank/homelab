output "nodes" {
  description = "Stable VM identities and reserved addresses."
  value       = local.nodes
}

output "ansible_inventory" {
  description = "Non-secret inventory; generate .local/inventory.json with make inventory."
  value = {
    all = {
      vars = {
        ansible_user               = "ubuntu"
        ansible_python_interpreter = "/usr/bin/python3"
        cluster_name               = var.cluster_name
        k3s_pod_cidr               = var.pod_cidr
        k3s_service_cidr           = var.service_cidr
        k3s_cluster_dns            = cidrhost(var.service_cidr, 10)
      }
      children = {
        k3s_cluster = {
          children = {
            k3s_server = {
              hosts = {
                for name, node in local.nodes : name => {
                  ansible_host  = node.address
                  proxmox_vm_id = node.vm_id
                } if node.role == "server"
              }
            }
            k3s_agents = {
              hosts = {
                for name, node in local.nodes : name => {
                  ansible_host  = node.address
                  proxmox_vm_id = node.vm_id
                } if node.role == "agent"
              }
            }
          }
        }
      }
    }
  }

  precondition {
    condition     = local.networks_disjoint
    error_message = "Node, pod, and service subnets must not overlap in either direction."
  }
}
