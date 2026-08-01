# ALANET IaC node deployment

This folder contains the repeatable path for adding a new VPN edge node without manual SSH installation.

Current implementation:

- Terraform provider: Hetzner Cloud.
- Terraform module: `infra/terraform/modules/vpn-node`.
- Bootstrap: Ansible playbook `infra/ansible/playbook-node.yml`.
- Runtime on node: isolated `remnawave/node` Docker Compose stack in `/opt/remnanode`.
- Optional monitoring: Beszel agent, disabled by default.
- Optional Remnawave registration: `infra/deploy/register-remnawave-node.sh`.

## One-command flow

From a Linux/macOS shell or WSL:

```bash
TF_VAR_hcloud_token="..." \
REMNANODE_SECRET_KEY="..." \
./infra/scripts/add-vpn-node.sh infra/terraform/environments/prod.tfvars
```

The command does:

1. `terraform init`
2. `terraform plan`
3. `terraform apply`
4. generates `infra/ansible/inventory.generated.ini`
5. runs Ansible bootstrap against the new node
6. optionally registers the node in Remnawave when `REGISTER_REMNAWAVE=true`

## Add a node

First add the planned node to `infra/node-registry.json`. This registry is the shared source for documentation, health-check expectations, Ansible inventory, Terraform planning, Remnawave sync and Beszel sync.

Render an Ansible inventory view:

```bash
python infra/scripts/render-node-registry.py --format ansible
```

Copy the example file:

```bash
cp infra/terraform/environments/prod.example.tfvars infra/terraform/environments/prod.tfvars
```

Add a new entry:

```hcl
nodes = {
  alanet-de-2 = {
    name        = "ALANET-DE-2"
    location    = "fsn1"
    server_type = "cx22"
    image       = "ubuntu-24.04"
    country     = "DE"
  }
}
```

Run only one host if the tfvars already contains several nodes:

```bash
TF_VAR_hcloud_token="..." \
REMNANODE_SECRET_KEY="..." \
ANSIBLE_LIMIT="alanet-de-2" \
./infra/scripts/add-vpn-node.sh infra/terraform/environments/prod.tfvars
```

## Optional Remnawave API registration

To create the Remnawave node record automatically:

```bash
TF_VAR_hcloud_token="..." \
REMNANODE_SECRET_KEY="..." \
REGISTER_REMNAWAVE=true \
REMNAWAVE_TOKEN="..." \
./infra/scripts/add-vpn-node.sh infra/terraform/environments/prod.tfvars
```

Defaults:

- `REMNAWAVE_BASE_URL=https://panel.alanet.ru`
- `CONFIG_PROFILE_NAME=COMMERCIAL-REALITY`
- `INBOUND_TAG=VLESS_TCP_REALITY`
- `NODE_PORT=2222`

The registration script is idempotent by Remnawave node name.

## Firewall model

Terraform creates a Hetzner firewall:

- SSH: allowed only from `admin_cidrs`.
- RemnaNode control port: allowed only from `control_plane_cidrs`.
- VPN public ports: open to the internet.

Ansible also configures UFW by default. This is safe for fresh Terraform-created nodes.

For existing shared VPS nodes, do not run firewall reset blindly. Use:

```bash
ansible-playbook -i inventory.ini infra/ansible/playbook-node.yml \
  --extra-vars "remnanode_secret_key=... manage_firewall=false"
```

## Secrets

Do not commit:

- Hetzner token.
- RemnaNode secret key.
- Remnawave API token.
- SSH private keys.
- Beszel key.

Pass them through environment variables, Ansible Vault, CI secrets, or a secret manager.

## Post-deploy verification

After bootstrap:

1. `ssh root@NODE_IP docker ps`
2. verify `remnanode-alanet` is running.
3. register/confirm the node in Remnawave.
4. attach it to the intended host/squad.
5. confirm `isConnected=true`.
6. add it to Beszel/monitoring if not automated.
7. test one subscription that includes the new location.
8. only then add the location to paid users.

## Rollback

If bootstrap fails:

```bash
terraform destroy -target='module.vpn_nodes["alanet-de-2"]' -var-file=infra/terraform/environments/prod.tfvars
```

If Remnawave registration was created but the node is unhealthy, remove the node from paid hosts/squads first, then delete or disable the node record in Remnawave.
