# ALANET operations runbook

All commands are executed on the primary VPS as `deploy`. Before a change, create a full backup and a targeted copy of every affected file. Never restart Docker itself for an ordinary application release.

## Safe service restart

| Component | Command | Verification | Rollback |
| --- | --- | --- | --- |
| Web | `cd /opt/alanet/deploy && sudo docker compose up -d --no-deps web` | `curl -fsS https://account.alanet.ru/` | restore previous source/image and recreate `web` |
| API | `cd /opt/alanet/deploy && sudo docker compose up -d --no-deps api` | `curl -fsS https://api.alanet.ru/health` | restore backend and recreate `api` |
| Worker | `cd /opt/alanet/deploy && sudo docker compose up -d --no-deps worker` | Celery `inspect ping`, then inspect logs | restore backend and recreate `worker` |
| Caddy | `sudo docker exec alanet-caddy-1 caddy validate --config /etc/caddy/Caddyfile` followed by `sudo docker exec alanet-caddy-1 caddy reload --config /etc/caddy/Caddyfile` | all public domains and TLS | restore Caddyfile and reload |
| Remnawave panel | restart only its container after a database/configuration backup | panel, API contract and all nodes | restore the pinned image/configuration |
| Subscription page | recreate only `remnawave-subscription-page` | one active subscription URL returns a VLESS list | restore its prior image/configuration |
| Node | restart only the ALANET RemnaNode container/service | panel reports connected and an ALANET client connects | restore the node compose/configuration |

Run `sudo systemctl start alanet-healthcheck.service` after every change. A release is incomplete until the service exits successfully.

## Shared VPS node replacement or removal

1. Do not edit, stop or replace an existing third-party VLESS listener.
2. Record listeners, containers, firewall rules and routing; save the ALANET compose/env and exact port bindings.
3. Remove the node from paid squads/hosts first, leaving other ALANET locations available.
4. Confirm that subscriptions no longer advertise the location.
5. Stop only the isolated ALANET RemnaNode container. Verify the third-party project before proceeding.
6. Add the replacement node with a distinct container, volume, network and listener port. Never reuse an occupied port.
7. Attach the new node to its host/squad, verify connection and perform a client test.
8. Roll back by restoring the host-to-node mapping and starting the previous isolated container.

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
