variable "project" {
  type = string
}

variable "name" {
  type = string
}

variable "location" {
  type = string
}

variable "server_type" {
  type = string
}

variable "image" {
  type = string
}

variable "country" {
  type = string
}

variable "role" {
  type = string
}

variable "ssh_key_ids" {
  type = list(string)
}

variable "admin_cidrs" {
  type = list(string)
}

variable "control_plane_cidrs" {
  type = list(string)
}

variable "vpn_public_tcp_ports" {
  type = list(string)
}

variable "vpn_public_udp_ports" {
  type = list(string)
}

variable "remnanode_control_port" {
  type = number
}

variable "extra_labels" {
  type    = map(string)
  default = {}
}
