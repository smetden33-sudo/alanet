# ALANET operations runbook

All commands are executed on the primary VPS as `deploy`. Before a change, create a full backup and a targeted copy of every affected file. Never restart Docker itself for an ordinary application release.

## Safe service restart

Production services use registry images built in CI. Do not run `docker compose build` on production.
Use `docker compose pull` and then `docker compose up -d --no-deps <service>`.

| Component | Command | Verification | Rollback |
| --- | --- | --- | --- |
| Web | `cd /opt/alanet/deploy && sudo docker compose pull web && sudo docker compose up -d --no-deps web` | `curl -fsS https://account.alanet.ru/` | restore previous image tag and recreate `web` |
| API | `cd /opt/alanet/deploy && sudo docker compose pull api && sudo docker compose up -d --no-deps api` | `curl -fsS https://api.alanet.ru/health` | restore previous image tag and recreate `api` |
| Worker | `cd /opt/alanet/deploy && sudo docker compose pull worker && sudo docker compose up -d --no-deps worker` | Celery `inspect ping`, then inspect logs | restore previous backend image tag and recreate `worker` |
| Caddy | `sudo docker exec alanet-caddy-1 caddy validate --config /etc/caddy/Caddyfile` followed by `sudo docker exec alanet-caddy-1 caddy reload --config /etc/caddy/Caddyfile` | all public domains and TLS | restore Caddyfile and reload |
| Remnawave panel | restart only its container after a database/configuration backup | panel, API contract and all nodes | restore the pinned image/configuration |
| Subscription page | recreate only `remnawave-subscription-page` | one active subscription URL returns a VLESS list | restore its prior image/configuration |
| Node | restart only the ALANET RemnaNode container/service | panel reports connected and an ALANET client connects | restore the node compose/configuration |

Run `sudo systemctl start alanet-healthcheck.service` after every change. A release is incomplete until the service exits successfully.

## Health-check Incident mode

`alanet-healthcheck.service` runs every five minutes and works in Incident mode. The goal is to avoid noisy Telegram alerts from one-off network glitches, while still escalating real production problems quickly.

Health states:

- `ok` — all checks pass.
- `warning` — a noisy check failed once or twice, but has not crossed the alert threshold. The service exits successfully and does not notify Telegram.
- `degraded` — a repeated noisy check crossed its threshold, or a non-critical location/node problem was found. The service exits with failure and sends one Telegram alert until the state changes.
- `incident` — a critical production dependency failed. The service exits with failure and sends one Telegram alert until the state changes.

When a `degraded` or `incident` state returns to `ok`, the admin receives an `ALANET RESOLVED` recovery notification.

Known checks are handled explicitly and summarized as `warning=` or `problem=` records. This prevents alerts such as "health-check failed on line 43/101" for expected operational failures.

Default thresholds:

- `ALANET_LOAD_FAILURE_THRESHOLD=3`
- `ALANET_API_FAILURE_THRESHOLD=3`
- `ALANET_PORTS_FAILURE_THRESHOLD=3`

State and diagnostic files:

- `/var/lib/alanet-monitor/health.state` — last state: `ok`, `warning`, `degraded` or `incident`.
- `/var/lib/alanet-monitor/health.summary` — latest human-readable state summary.
- `/var/lib/alanet-monitor/load.failures` — consecutive load failures.
- `/var/lib/alanet-monitor/api.failures` — consecutive API health failures.
- `/var/lib/alanet-monitor/ports.failures` — consecutive host-port failures.

A counter is reset only when that specific check passes again.

Thresholded/noisy checks:

- API `/health`.
- Host ports from Remnawave `/api/hosts`.
- Server load.

Immediate critical checks:

- public site, account cabinet, Remnawave panel and subscription routing;
- TLS certificates;
- disk and memory limits;
- Telegram webhook URL;
- billing subscription URL validity;
- required production containers.

Expected Remnawave nodes are read from `infra/node-registry.json` when the file exists on production. Host-port checks are intentionally read live from Remnawave `/api/hosts`, so a newly added host is monitored without editing the shell script.

Manual inspection:

```bash
sudo systemctl start alanet-healthcheck.service
sudo journalctl -u alanet-healthcheck.service -n 120 --no-pager -o cat
sudo cat /var/lib/alanet-monitor/health.state
sudo sed -n '1,80p' /var/lib/alanet-monitor/health.summary
```

## Shared VPS node replacement or removal

1. Do not edit, stop or replace an existing third-party VLESS listener.
2. Record listeners, containers, firewall rules and routing; save the ALANET compose/env and exact port bindings.
3. Remove the node from paid squads/hosts first, leaving other ALANET locations available.
4. Confirm that subscriptions no longer advertise the location.
5. Stop only the isolated ALANET RemnaNode container. Verify the third-party project before proceeding.
6. Add the replacement node with a distinct container, volume, network and listener port. Never reuse an occupied port.
7. Attach the new node to its host/squad, verify connection and perform a client test.
8. Roll back by restoring the host-to-node mapping and starting the previous isolated container.

## Terraform/Ansible node deployment

Fresh cloud nodes should be added through IaC, not by manual SSH installation.

1. Add the node to `infra/terraform/environments/prod.tfvars`.
2. Run the wrapper from Linux/macOS/WSL:

```bash
TF_VAR_hcloud_token="..." \
REMNANODE_SECRET_KEY="..." \
REGISTER_REMNAWAVE=true \
REMNAWAVE_TOKEN="..." \
./infra/scripts/add-vpn-node.sh infra/terraform/environments/prod.tfvars
```

3. Confirm the generated Ansible inventory at `infra/ansible/inventory.generated.ini`.
4. Confirm the Remnawave node is connected.
5. Attach the node to the intended host/squad.
6. Add the node to Beszel/monitoring if it was not enabled by Ansible variables.
7. Run `alanet-healthcheck.service` on production and test one subscription before exposing the location to paid users.

## Off-host build and registry release

Production web/API images are built outside the VPS by CI and pushed to a registry.
The production `.env` points `ALANET_WEB_IMAGE` and `ALANET_BACKEND_IMAGE` at the published tags.

GitHub Actions secrets required for auto-deploy:

- `PROD_HOST`
- `PROD_USER`
- `PROD_SSH_PORT`
- `PROD_SSH_KEY`

Release flow:

1. Push to `main` or run the CI workflow manually.
2. CI builds `web` and `backend` images and publishes `latest` plus a commit SHA tag to GHCR.
3. Production runs `docker compose pull web api worker`.
4. Production runs `docker compose up -d --no-deps web api worker`.
5. CI performs safe Docker cleanup without volumes before/after deploy.
6. `alanet-healthcheck.service` must return `ok`; CI retries it up to five times to tolerate short restart/load spikes.

Rollback:

1. Set `ALANET_WEB_IMAGE` / `ALANET_BACKEND_IMAGE` to the previous SHA tag.
2. Pull the previous images.
3. Recreate `web`, `api` and `worker`.
4. Re-run health-check.

For existing shared VPS hosts, do not run the firewall role unless all third-party ports are known and explicitly allowed. Use `manage_firewall=false` for shared hosts.

## Remnawave sync from node registry

`infra/node-registry.json` is the source of truth for ALANET nodes and hosts. Remnawave is checked against it before and after node changes.

Safe drift report:

```bash
python3 /opt/alanet/infra/scripts/remnawave-registry-sync.py \
  --registry /opt/alanet/infra/node-registry.json \
  --env-file /opt/alanet/deploy/.env
```

Admin Telegram command:

```text
/remnawave_sync
```

The sync currently works in report-only mode for Remnawave writes. It compares:

- registry node UUID/name/country/status;
- Remnawave `/api/nodes`;
- registry host UUID/name/IP/public port;
- Remnawave `/api/hosts`;
- host-to-node bindings.

Critical drift examples:

- active registry node or host is missing in Remnawave;
- Remnawave host IP or public port differs from registry;
- host is disabled;
- host is not bound to the expected node UUID.

Warning drift examples:

- display name differs;
- country code differs;
- node is disconnected;
- Remnawave has an extra enabled host or node not marked active in registry.

`--apply` is intentionally blocked when drift requires Remnawave writes. Enable write-sync only after testing the exact Remnawave create/update/delete API contract in staging and preparing rollback for hosts/squads.

## Production disk hygiene

The primary VPS has a small root disk. Docker builds can temporarily push disk usage above the health-check threshold. A weekly safe prune is installed on production:

- `/usr/local/sbin/alanet-docker-prune`
- `alanet-docker-prune.timer`

It removes only old build cache, unused images and stopped containers. It does not remove Docker volumes.

Before large releases, check:

```bash
df -h /
sudo docker system df
sudo du -xhd2 /var/lib/containerd | sort -h | tail
```

If `/` remains above 80-85% after prune, prefer increasing the VPS disk or moving Docker image builds to CI/off-host build runners. Do not run `docker system prune --volumes` on production unless a verified backup and rollback plan exists.

## Weekly restore-test

Backups are not considered reliable until a fresh dump is restored. Production runs `alanet-restore-test.timer` weekly.

The restore-test:

1. selects the newest `/var/backups/alanet/alanet-*.tar.gz`;
2. extracts `billing.sql.gz`;
3. starts a temporary `postgres:16-alpine` container;
4. restores the dump with `ON_ERROR_STOP=1`;
5. counts public tables and key records;
6. sends a Telegram report to the admin;
7. removes the temporary container and work directory.

Manual run:

```bash
sudo systemctl start alanet-restore-test.service
sudo journalctl -u alanet-restore-test.service -n 80 --no-pager -o cat
```

## Staging for payments and provisioning

Staging is documented in `docs/STAGING-RUNBOOK.md`.

Minimum acceptance criteria before a payment/provisioning change reaches production:

1. YooKassa test webhook is configured for `https://api-staging.alanet.ru/webhooks/yookassa`.
2. Telegram staging bot webhook is configured for `https://api-staging.alanet.ru/webhooks/telegram`.
3. Test payment contains `metadata.order_id`, `metadata.customer_id` and `metadata.plan_id`.
4. Successful test payment provisions or extends a Remnawave user in the staging/internal squad.
5. Replayed webhook does not issue a second subscription.
6. Manual retry provisions an order from `PROVISIONING_FAILED` without changing the paid period.

## YooKassa financial reconciliation

Commercial payment state is checked separately from ordinary provisioning retries.

Manual Telegram command:

```text
/finance [days]
```

Daily worker task:

- Celery task: `app.worker.daily_finance_reconciliation`
- Schedule: every day at `06:20` in the worker timezone.
- Mode: report-only.

The reconciliation checks local DB payments against YooKassa API:

- local payment status vs YooKassa status;
- local amount vs YooKassa amount;
- YooKassa `metadata.order_id`, `metadata.customer_id`, `metadata.plan_id`;
- `payment.succeeded` in YooKassa but local order/subscription is not `ACTIVE`;
- local paid order is `ACTIVE`, but local payment is not `succeeded`.

The report never activates, revokes or refunds access automatically. Fixes should go through the existing provisioning retry/admin flow after the mismatch is understood.

## Customer data deletion and retention

Deletion requests must be authenticated through the linked Telegram account or another verified channel. Record the request without copying subscription URLs or payment secrets into support messages.

1. Revoke/disable the Remnawave user and invalidate web sessions and bind/login tokens.
2. Remove Telegram username and other optional profile data; replace the billing email with a non-deliverable anonymized value when financial records must be retained.
3. Delete unused tokens immediately. Web login tokens live for 15 minutes, bind tokens for 7 days and web sessions for no more than 30 days.
4. Operational notification/audit records should be retained for 90 days unless an incident requires a documented extension.
5. Orders, payments and refund records are retained only for the period required by accounting, tax and consumer law. The exact statutory period must be confirmed with the real seller's lawyer/accountant before public website checkout is enabled.
6. Record completion in the audit log and confirm the result to the requester without exposing internal identifiers.

## Access rotation

Rotate one credential at a time: create the replacement, verify it in parallel, update the encrypted production environment, restart only the dependent service, run health-check, then revoke the old credential. SSH keys require a second verified session before removal of the previous key. Payment and Telegram credentials require updating the external provider and production configuration in a coordinated maintenance window.

