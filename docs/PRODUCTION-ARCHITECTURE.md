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
Redis/Celery beat → billing worker → retry failed provisioning / reconcile payments
```

## Primary VPS

- Host: `78.17.54.252`
- SSH deployment user: `deploy`
- Application root: `/opt/alanet`
- Compose file: `/opt/alanet/deploy/compose.yml`
- Runtime images: pulled from GHCR via `ALANET_WEB_IMAGE` and `ALANET_BACKEND_IMAGE`
- Runtime services: web, api, billing worker, Caddy, billing PostgreSQL, billing Redis, Remnawave, Remnawave PostgreSQL, Remnawave Redis, subscription page, Remnawave node.

The API uses `https://panel.alanet.ru` as its Remnawave base URL. This is required by the current panel configuration; the internal HTTP endpoint closes API connections.

## Public domains

| Domain | Purpose |
| --- | --- |
| `alanet.ru` | Public landing page |
| `account.alanet.ru` | Account and checkout UI |
| `api.alanet.ru` | Billing API and Telegram/YooKassa webhooks |
| `panel.alanet.ru` | Remnawave panel |
| `sub.alanet.ru` | Remnawave subscription page |

YooKassa production is enabled in billing API. The API credentials are stored only in the production `.env`; the `payment.succeeded` notification must be configured in the YooKassa merchant dashboard to `https://api.alanet.ru/webhooks/yookassa`.

The webhook fetches the payment from YooKassa and requires an exact match for status, RUB amount, `order_id`, `customer_id` and `plan_id`. A notification payload alone is never trusted.

Authenticated customers renew through `POST /api/v1/me/checkout`. The endpoint accepts only a paid plan slug, resolves the customer from the HttpOnly web session, and uses the email and Telegram identity already attached to that customer. The browser never supplies an email for renewal.

On 2026-07-28 the `start` checkout was verified end-to-end with the YooKassa test shop: successful card confirmation, provider-side payment verification, idempotent webhook replay, Remnawave provisioning and an active subscription. Live credentials were restored after the test.

All domains use Caddy-managed Let's Encrypt certificates. Sensitive paths are blocked with HTTP 404.

## Subscription model

The billing database stores one `Customer` and one `Subscription` per Telegram account. Each `Plan` stores duration, traffic, devices and a Remnawave internal squad UUID. Paid subscriptions currently resolve to Finland, Germany, Czechia, Sweden, Poland, Spain and Latvia; trial subscriptions remain restricted to Czechia.

Telegram identity is keyed by the immutable numeric `telegram_id`; `@username` is display-only and may change. Billing is the identity bridge: `telegram_id → Customer.id → Subscription.remnawave_user_id`. Remnawave does not authenticate Telegram directly. Its stable technical username is derived from `Customer.id` (`customer_<uuid prefix>`), which avoids exposing Telegram identifiers and remains unchanged when the Telegram username changes. A bot checkout refuses to merge an email that is already linked to another Telegram ID and writes an audit entry when the identity is first registered.

- `trial`: 1 day, unlimited, 1 device, `TRIAL-CZ`.
- `start`: 30 days, unlimited, 1 device, `PAID-USERS`.
- `calm`: 90 days, unlimited, 1 device, `PAID-USERS`.
- `year`: 365 days, unlimited, 1 device, `PAID-USERS`.

On a new subscription the API calls `POST /api/users`. On renewal or plan change it calls `PATCH /api/users` by the stored Remnawave UUID and updates expiry, limits and active internal squads.

On 2026-07-28 this identity chain was verified end-to-end with a new synthetic Telegram client. The first `start` payment created one Customer and one Remnawave user; a second `start` payment with the same Telegram ID but a changed `@username` reused both records and extended the existing expiry by exactly 30 days. An attempted checkout using the same email with another Telegram ID was rejected before payment creation. Live YooKassa credentials were restored after the test.

Failed provisioning is stored as `PROVISIONING_FAILED`. `alanet-worker-1` checks the retry queue every minute and accepts paid orders only when their local payment is confirmed; free trial/admin grants remain eligible without a payment. The target expiry is persisted on the order and reused on every attempt. A PostgreSQL advisory lock serializes webhook, worker and `/retry <order_id>` execution for the same order, so a retry cannot extend an active subscription twice.

## Rollback

Before production changes, copy the affected files to `/opt/alanet/backups/<change>-<UTC timestamp>`. Full daily archives are written to `/var/backups/alanet` by `alanet-backup.timer` and contain billing/Remnawave PostgreSQL dumps plus deployment configuration. The last known-good image and configuration must be retained until the post-deploy health check passes. Production releases should switch image tags, not rebuild containers on the VPS.
