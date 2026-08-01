resource "hcloud_ssh_key" "deploy" {
  name       = var.ssh_key_name
  public_key = file(pathexpand(var.ssh_public_key_path))
}

module "vpn_nodes" {
  source = "./modules/vpn-node"

  for_each = var.nodes

  project                 = var.project
  name                    = each.value.name
  location                = each.value.location
  server_type             = each.value.server_type
  image                   = each.value.image
  country                 = each.value.country
  role                    = each.value.role
  ssh_key_ids             = [hcloud_ssh_key.deploy.id]
  admin_cidrs             = var.admin_cidrs
  control_plane_cidrs     = var.control_plane_cidrs
  vpn_public_tcp_ports    = var.vpn_public_tcp_ports
  vpn_public_udp_ports    = var.vpn_public_udp_ports
  remnanode_control_port  = var.remnanode_control_port
  extra_labels            = each.value.labels
}

locals {
  ansible_inventory = templatefile("${path.module}/templates/inventory.ini.tftpl", {
    nodes = {
      for key, node in module.vpn_nodes : key => {
        name       = node.name
        public_ip  = node.public_ip
        country    = node.country
        location   = node.location
        node_port  = var.remnanode_control_port
      }
    }
  })
}

resource "local_file" "ansible_inventory" {
  filename = "${path.module}/../ansible/inventory.generated.ini"
  content  = local.ansible_inventory
}
