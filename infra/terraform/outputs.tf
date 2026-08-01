output "vpn_nodes" {
  description = "Created VPN edge nodes."
  value = {
    for key, node in module.vpn_nodes : key => {
      name      = node.name
      public_ip = node.public_ip
      ipv6      = node.ipv6
      country   = node.country
      location  = node.location
    }
  }
}

output "ansible_inventory_path" {
  description = "Generated Ansible inventory path."
  value       = local_file.ansible_inventory.filename
}
