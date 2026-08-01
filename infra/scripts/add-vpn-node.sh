#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./infra/scripts/add-vpn-node.sh <tfvars-file>

Required environment:
  TF_VAR_hcloud_token       Hetzner Cloud token
  REMNANODE_SECRET_KEY      RemnaNode secret key

Optional environment:
  SSH_PRIVATE_KEY           SSH key for Ansible, default ~/.ssh/alanet_deploy_ed25519
  ANSIBLE_LIMIT             Limit bootstrap to one inventory host, e.g. alanet-de-2
  REGISTER_REMNAWAVE        true/false, default false
  REMNAWAVE_TOKEN           Required when REGISTER_REMNAWAVE=true
  REMNAWAVE_BASE_URL        default https://panel.alanet.ru
  CONFIG_PROFILE_NAME       default COMMERCIAL-REALITY
  INBOUND_TAG               default VLESS_TCP_REALITY

Example:
  TF_VAR_hcloud_token=... REMNANODE_SECRET_KEY=... \
    ./infra/scripts/add-vpn-node.sh infra/terraform/environments/prod.tfvars
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || $# -ne 1 ]]; then
  usage
  exit $([[ $# -eq 1 ]] && echo 0 || echo 1)
fi

tfvars_file="$1"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
terraform_dir="${repo_root}/infra/terraform"
ansible_dir="${repo_root}/infra/ansible"
ssh_private_key="${SSH_PRIVATE_KEY:-${HOME}/.ssh/alanet_deploy_ed25519}"

if [[ "${tfvars_file}" = /* ]]; then
  tfvars_path="${tfvars_file}"
else
  tfvars_path="${repo_root}/${tfvars_file}"
fi

if [[ ! -f "${tfvars_path}" ]]; then
  echo "tfvars file not found: ${tfvars_path}" >&2
  exit 1
fi

: "${TF_VAR_hcloud_token:?TF_VAR_hcloud_token is required}"
: "${REMNANODE_SECRET_KEY:?REMNANODE_SECRET_KEY is required}"

cd "${terraform_dir}"
terraform init
terraform plan -var-file="${tfvars_path}"
terraform apply -auto-approve -var-file="${tfvars_path}"

inventory="${ansible_dir}/inventory.generated.ini"
if [[ ! -f "${inventory}" ]]; then
  echo "Generated inventory not found: ${inventory}" >&2
  exit 1
fi

ansible_args=(-i "${inventory}" "${ansible_dir}/playbook-node.yml" --private-key "${ssh_private_key}" --extra-vars "remnanode_secret_key=${REMNANODE_SECRET_KEY}")
if [[ -n "${ANSIBLE_LIMIT:-}" ]]; then
  ansible_args+=(--limit "${ANSIBLE_LIMIT}")
fi

ansible-playbook "${ansible_args[@]}"

if [[ "${REGISTER_REMNAWAVE:-false}" == "true" ]]; then
  : "${REMNAWAVE_TOKEN:?REMNAWAVE_TOKEN is required when REGISTER_REMNAWAVE=true}"
  terraform output -json vpn_nodes | jq -r 'to_entries[] | @base64' | while read -r row; do
    node_json="$(printf '%s' "${row}" | base64 -d)"
    export NODE_NAME
    export NODE_ADDRESS
    export NODE_COUNTRY
    NODE_NAME="$(jq -r '.value.name' <<<"${node_json}")"
    NODE_ADDRESS="$(jq -r '.value.public_ip' <<<"${node_json}")"
    NODE_COUNTRY="$(jq -r '.value.country' <<<"${node_json}")"
    NODE_PORT="${REMNANODE_NODE_PORT:-2222}" \
      REMNAWAVE_TOKEN="${REMNAWAVE_TOKEN}" \
      REMNAWAVE_BASE_URL="${REMNAWAVE_BASE_URL:-https://panel.alanet.ru}" \
      CONFIG_PROFILE_NAME="${CONFIG_PROFILE_NAME:-COMMERCIAL-REALITY}" \
      INBOUND_TAG="${INBOUND_TAG:-VLESS_TCP_REALITY}" \
      "${repo_root}/infra/deploy/register-remnawave-node.sh"
  done
fi

echo "ALANET node deployment finished."
