locals {
  labels = merge(
    {
      project = var.project
      role    = var.role
      country = var.country
      managed = "terraform"
    },
    var.extra_labels
  )
}

resource "hcloud_firewall" "node" {
  name = "${var.name}-fw"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = var.admin_cidrs
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = tostring(var.remnanode_control_port)
    source_ips = var.control_plane_cidrs
  }

  dynamic "rule" {
    for_each = toset(var.vpn_public_tcp_ports)
    content {
      direction  = "in"
      protocol   = "tcp"
      port       = rule.value
      source_ips = ["0.0.0.0/0", "::/0"]
    }
  }

  dynamic "rule" {
    for_each = toset(var.vpn_public_udp_ports)
    content {
      direction  = "in"
      protocol   = "udp"
      port       = rule.value
      source_ips = ["0.0.0.0/0", "::/0"]
    }
  }
}

resource "hcloud_server" "node" {
  name        = var.name
  image       = var.image
  server_type = var.server_type
  location    = var.location
  ssh_keys    = var.ssh_key_ids
  labels      = local.labels

  firewall_ids = [hcloud_firewall.node.id]

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }
}
