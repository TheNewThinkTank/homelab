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
        ansible_ssh_common_args    = "-o ProxyJump=${var.host_ssh_alias} -o UserKnownHostsFile=${abspath("${path.module}/../../.local/known_hosts")} -o StrictHostKeyChecking=yes -o UpdateHostKeys=no"
        cluster_name               = var.cluster_name
        pn51_host_ssh_alias        = var.host_ssh_alias
        k3s_pod_cidr               = var.pod_cidr
        k3s_service_cidr           = var.service_cidr
        k3s_cluster_dns            = cidrhost(var.service_cidr, 10)
        k3s_api_service_ip         = cidrhost(var.service_cidr, 1)
        k3s_node_cidr              = var.network_cidr
        k3s_nat_gateway            = var.gateway
        homelab_data_device        = "/dev/vdb"
        homelab_data_mount         = "/srv/homelab-data"
      }
      children = {
        k3s_cluster = {
          children = {
            k3s_server = {
              hosts = {
                for name, node in local.nodes : name => {
                  ansible_host = node.address
                  libvirt_name = name
                  libvirt_mac  = node.mac
                } if node.role == "server"
              }
            }
            k3s_agents = {
              hosts = {
                for name, node in local.nodes : name => {
                  ansible_host = node.address
                  libvirt_name = name
                  libvirt_mac  = node.mac
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
