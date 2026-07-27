# ALANET production architecture

This document describes the production topology without credentials or private keys.

## Traffic and control flow

```text
Client
  ├─ alanet.ru / account.alanet.ru ── Caddy ── web (landing + checkout)
  ├─ api.alanet.ru ───────────────── Caddy ── billing API (FastAPI)
  ├─ panel.alanet.ru ─────────────── Caddy ── Remnawave panel
  └─ sub.alanet.ru ───────────────── Caddy ── Remnawave subscription page

Telegram → api.alanet.ru/webhooks/telegram → billing API → PostgreSQL/Redis
                                               └──────────→ Remnawave API
YooKassa → api.alanet.ru/webhooks/yookassa → billing API → Remnawave API
```

## Primary VPS

- Host: `78.17.54.252`
- SSH deployment user: `deploy`
- Application root: `/opt/alanet`
- Compose file: `/opt/alanet/deploy/compose.yml`
- Runtime services: web, api, Caddy, billing PostgreSQL, billing Redis, Remnawave, Remnawave PostgreSQL, Remnawave Redis, subscription page, Remnawave node.

The API uses `https://panel.alanet.ru` as its Remnawave base URL. This is required by the current panel configuration; the internal HTTP endpoint closes API connections.

## Public domains

| Domain | Purpose |
| --- | --- |
| `alanet.ru` | Public landing page |
| `account.alanet.ru` | Account and checkout UI |
| `api.alanet.ru` | Billing API and Telegram/YooKassa webhooks |
| `panel.alanet.ru` | Remnawave panel |
| `sub.alanet.ru` | Remnawave subscription page |

All domains use Caddy-managed Let's Encrypt certificates. Sensitive paths are blocked with HTTP 404.

## Subscription model

The billing database stores one `Customer` and one `Subscription` per Telegram account. Each `Plan` stores duration, traffic, devices and a Remnawave internal squad UUID. Paid subscriptions currently resolve to Finland, Germany, Czechia, Sweden and Poland; trial subscriptions remain restricted to Czechia.

- `trial`: 1 day, unlimited, 1 device, `TRIAL-CZ`.
- `start`: 30 days, unlimited, 1 device, `PAID-USERS`.
- `calm`: 90 days, unlimited, 1 device, `PAID-USERS`.
- `year`: 365 days, unlimited, 1 device, `PAID-USERS`.

On a new subscription the API calls `POST /api/users`. On renewal or plan change it calls `PATCH /api/users` by the stored Remnawave UUID and updates expiry, limits and active internal squads.

## Rollback

Before production changes, copy the affected files to `/opt/alanet/backups/<change>-<UTC timestamp>`. Full daily archives are written to `/var/backups/alanet` by `alanet-backup.timer` and contain billing/Remnawave PostgreSQL dumps plus deployment configuration. The last known-good image and configuration must be retained until the post-deploy health check passes.
