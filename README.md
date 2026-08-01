# ALANET — коммерческий MVP на Remnawave

Проект ALANET — это control plane для продажи и выдачи VPN-доступа через Remnawave/Xray.

В составе MVP:

- публичный сайт и тарифы;
- FastAPI backend для заказов, оплат и provisioning;
- Telegram-бот для клиентского сценария и административных команд;
- интеграция YooKassa;
- PostgreSQL, Redis/Celery;
- Caddy reverse proxy;
- Remnawave panel, subscription page и мульти-нодовая инфраструктура.

## Локальный запуск сайта

```powershell
npm.cmd install
npm.cmd run dev
```

Сайт откроется на `http://localhost:3000`.

## Локальный запуск backend

1. Скопировать `.env.example` в `.env`.
2. Заполнить локальные значения и тестовые токены.
3. Запустить:

```powershell
docker compose up --build
```

API: `http://localhost:8000`.

Health endpoint: `/health`.

## Production

Основной production-контур описан в:

- `docs/PRODUCTION-ARCHITECTURE.md`
- `docs/PRODUCTION-INVENTORY.md`
- `docs/OPERATIONS-RUNBOOK.md`

Production web/API images are built in CI and published to GHCR. The VPS only pulls готовые образы и запускает их через `docker compose pull` / `docker compose up -d`.

После каждого изменения на production запускать:

```bash
sudo systemctl start alanet-healthcheck.service
sudo journalctl -u alanet-healthcheck.service -n 80 --no-pager -o cat
```

## Staging

Staging для оплат и provisioning описан в:

- `deploy/compose.staging.yml`
- `deploy/.env.staging.example`
- `docs/STAGING-RUNBOOK.md`

Staging должен использовать отдельные:

- тестовый магазин YooKassa;
- Telegram-бот;
- PostgreSQL volume;
- Redis;
- ограниченный Remnawave API token;
- staging/internal squads в Remnawave.

## Сценарий оплаты

Платёжный поток:

```text
CREATED -> PAYMENT_PENDING -> PROVISIONING -> ACTIVE
```

Webhook YooKassa не считается доказательством оплаты сам по себе. Backend повторно запрашивает платёж через API YooKassa и сверяет:

- статус платежа;
- сумму;
- валюту RUB;
- `metadata.order_id`;
- `metadata.customer_id`;
- `metadata.plan_id`.

Если Remnawave временно недоступен, заказ переводится в `PROVISIONING_FAILED`, после чего retry-механизм может повторить выдачу без изменения оплаченного периода.

## Telegram

Клиент регистрируется по стабильному Telegram ID. Username используется только как отображаемое имя и не должен быть основным идентификатором, потому что пользователь может его изменить.

Администратор привязан к Telegram ID `6137733861`.

## Проверки

```powershell
npm.cmd run lint
npm.cmd run build
python -m compileall backend/app
```

Для staging дополнительно проверить:

- тестовый платёж YooKassa;
- повторный webhook;
- двойной клик оплаты;
- сбой Remnawave после успешного платежа;
- ручной retry provisioning;
- продление активной и истёкшей подписки.
