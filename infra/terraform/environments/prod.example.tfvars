project = "alanet"

# Pass the real token through TF_VAR_hcloud_token, not in this file.
# hcloud_token = "..."

ssh_key_name        = "alanet-deploy"
ssh_public_key_path = "~/.ssh/alanet_deploy_ed25519.pub"

# Restrict this to trusted admin IPs before applying in production.
admin_cidrs = ["203.0.113.10/32"]

# ALANET production control plane public IP.
control_plane_cidrs = ["78.17.54.252/32"]

vpn_public_tcp_ports = ["443"]
vpn_public_udp_ports = ["443"]

remnanode_control_port = 2222

nodes = {
  alanet-de-2 = {
    name        = "ALANET-DE-2"
    location    = "fsn1"
    server_type = "cx22"
    image       = "ubuntu-24.04"
    country     = "DE"
  }
}
