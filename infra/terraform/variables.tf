variable "hcloud_token" {
  description = "Hetzner Cloud API token. Pass via TF_VAR_hcloud_token or a secure CI secret."
  type        = string
  sensitive   = true
}

variable "project" {
  description = "Project label used for resources."
  type        = string
  default     = "alanet"
}

variable "ssh_key_name" {
  description = "Name of the SSH key registered in Hetzner Cloud."
  type        = string
  default     = "alanet-deploy"
}

variable "ssh_public_key_path" {
  description = "Path to the public SSH key used for node bootstrap."
  type        = string
  default     = "~/.ssh/alanet_deploy_ed25519.pub"
}

variable "admin_cidrs" {
  description = "CIDRs allowed to connect to SSH."
  type        = list(string)
}

variable "control_plane_cidrs" {
  description = "CIDRs allowed to connect to RemnaNode control port."
  type        = list(string)
}

variable "vpn_public_tcp_ports" {
  description = "Public TCP ports used by VPN inbounds."
  type        = list(string)
  default     = ["443"]
}

variable "vpn_public_udp_ports" {
  description = "Public UDP ports used by VPN inbounds."
  type        = list(string)
  default     = ["443"]
}

variable "remnanode_control_port" {
  description = "RemnaNode control port."
  type        = number
  default     = 2222
}

variable "nodes" {
  description = "VPN edge nodes keyed by stable inventory name."
  type = map(object({
    name        = string
    location    = string
    server_type = optional(string, "cx22")
    image       = optional(string, "ubuntu-24.04")
    country     = string
    role        = optional(string, "vpn-edge")
    labels      = optional(map(string), {})
  }))
}
