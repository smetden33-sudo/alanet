output "name" {
  value = hcloud_server.node.name
}

output "public_ip" {
  value = hcloud_server.node.ipv4_address
}

output "ipv6" {
  value = hcloud_server.node.ipv6_address
}

output "country" {
  value = var.country
}

output "location" {
  value = var.location
}

output "server_id" {
  value = hcloud_server.node.id
}
