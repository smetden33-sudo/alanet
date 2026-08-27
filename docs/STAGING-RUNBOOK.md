# ALANET staging runbook

Цель staging: безопасно проверять оплату YooKassa, Telegram-сценарий и provisioning в Remnawave до изменения production.

## Контур

- Web: `https://staging.alanet.ru` и `https://account-staging.alanet.ru`
- API: `https://api-staging.alanet.ru`
- Docker Compose project: `alanet-staging`
- Compose file: `deploy/compose.staging.yml`
- Environment template: `deploy/.env.staging.example`
- Database: отдельный PostgreSQL volume `billing-staging-data`
- Redis: отдельный контейнер staging
- Remnawave: mock service `remnawave-mock` by default
- Node profile: `ALANET-STAGING-01`

## Текущее состояние

Дата фиксации: 26.08.2026.

- Staging web/API/DB/Redis/mock Remnawave подняты на production VPS отдельным Docker Compose project `alanet-staging`.
- Production volume’ы не используются staging-контуром.
- `node-registry.json` смонтирован в staging API/worker read-only.
- YooKassa в staging пока намеренно выключена: `YOOKASSA_ENABLED=false`.
- YooKassa test shop подключён: `YOOKASSA_ENABLED=true`.
- Telegram staging bot подключён: `alanet_staging_bot`.
- Staging status: `ok`.
- Допустимый статус `/api/v1/status` для phase 1 без YooKassa: `degraded` только с причиной `payments: YooKassa is not configured`.
- Установлены команды `alanet-staging-configure-secrets` и `alanet-staging-e2e-check`.
- Dry-run E2E проходит: Telegram ID → Customer → Order → Subscription → mock Remnawave user.
- Paid checkout создаёт YooKassa test payment и сохраняет заказ в staging DB.

## Правила безопасности

1. Использовать только тестовые ключи YooKassa.
2. Использовать отдельного staging Telegram-бота.
3. По умолчанию использовать mock Remnawave. Реальный staging Remnawave включать только отдельным токеном с минимальными правами.
4. Не подключать staging к production-боту.
5. Не использовать production `.env` как основу без ручной очистки секретов.
6. Не отправлять staging-ссылки реальным клиентам.

## Первый запуск

```bash
cd /opt/alanet/deploy
cp .env.staging.example .env.staging
chmod 600 .env.staging
```

Заполнить `.env.staging`:

- `STAGING_BILLING_DB_PASSWORD`
- `YOOKASSA_SHOP_ID`
- `YOOKASSA_SECRET_KEY`
- `REMNAWAVE_TOKEN`
- `REMNAWAVE_SQUAD_ID`
- `REMNAWAVE_TRIAL_SQUAD_ID`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `TELEGRAM_BOT_USERNAME`

Безопасный способ включить test YooKassa и staging Telegram bot:

```bash
sudo ALANET_STAGING_YOOKASSA_SHOP_ID=<test-shop-id> \
  ALANET_STAGING_YOOKASSA_SECRET_KEY=<test-secret-key> \
  ALANET_STAGING_TELEGRAM_BOT_TOKEN=<staging-bot-token> \
  ALANET_STAGING_TELEGRAM_BOT_USERNAME=<staging-bot-username> \
  alanet-staging-configure-secrets
```

Скрипт обновляет только `.env.staging` и откажется принимать:

- `live_*` YooKassa secret key;
- не `test_*` YooKassa secret key;
- production Telegram username `alanet_bot`.

По умолчанию:

- `REMNAWAVE_BASE_URL=http://remnawave-mock:8080`
- `REMNAWAVE_SQUAD_ID=00000000-0000-4000-8000-000000000301`
- `REMNAWAVE_TRIAL_SQUAD_ID=00000000-0000-4000-8000-000000000302`
- `STAGING_NODE_PROFILE=ALANET-STAGING-01`

Запустить:

```bash
sudo docker compose -f compose.staging.yml --env-file .env.staging up -d --build
sudo docker compose -f compose.staging.yml --env-file .env.staging ps
```

Если Caddy уже обслуживает production, после добавления staging-доменов:

```bash
cd /opt/alanet/deploy
sudo docker compose config >/tmp/alanet-compose.config
sudo docker compose up -d --no-deps --force-recreate caddy
```

На текущем production Caddy admin API выключен, поэтому `caddy reload` внутри контейнера не используется.

## Smoke-check

```bash
cd /opt/alanet/deploy
/opt/alanet/deploy/staging-smoke-check.sh
```

Ожидаемый phase 1 результат:

```text
staging_site=200
staging_api_health_status=ok
staging_api_status_status=degraded
payments: YooKassa is not configured
remnawave_mock_status=ok
staging_smoke=ok
```

## Webhooks

YooKassa:

- event: `payment.succeeded`
- URL: `https://api-staging.alanet.ru/webhooks/yookassa`
- Управление YooKassa webhooks через shop ID + secret key недоступно: API возвращает `Authentication type is not allowed`.
- Webhook нужно включить в кабинете YooKassa test shop или через OAuth-интеграцию с правом управления webhooks.

Telegram:

- URL: `https://api-staging.alanet.ru/webhooks/telegram`
- secret token должен совпадать с `TELEGRAM_WEBHOOK_SECRET`.

## End-to-end тест

Dry-run без реальной YooKassa:

```bash
alanet-staging-e2e-check dry-run
```

Проверяет:

- доступность staging site/API;
- создание тестового клиента по Telegram ID;
- создание заказа;
- provisioning подписки;
- создание пользователя в mock Remnawave;
- сохранение subscription URL.

Paid checkout после включения test YooKassa:

```bash
alanet-staging-e2e-check paid-checkout
```

Этот режим создаёт тестовый заказ и возвращает YooKassa confirmation URL. После оплаты тестовой картой нужно проверить webhook и idempotency.

Проверено 26.08.2026:

```text
paid_checkout=created
local_order_status=PAYMENT_PENDING
local_payment_status=pending
remote_payment_status=pending
metadata_order_id_ok=True
metadata_customer_id_ok=True
metadata_plan_id_ok=True
confirmation_present=True
```

Full successful payment E2E проверен 26.08.2026:

```text
YooKassa test payment: succeeded
Webhook event: PROCESSED
Order: ACTIVE
Payment: succeeded
Subscription: ACTIVE
Webhook replay: duplicate
Expiry unchanged after replay: yes
```

Проверенный payment ID: `322126ca-000f-5001-9000-10e365df42a7`.
Проверенный order ID: `a5e1f29d-1012-4d67-86b6-c09b1446ac16`.

Если YooKassa test credentials ещё не включены, ожидаемый результат:

```text
paid_checkout=failed
http_status=503
response={"detail":"payment integration is not configured"}
hint=enable staging YooKassa test credentials with alanet-staging-configure-secrets
```

1. Открыть staging-бота и выполнить `/start`.
2. Выбрать тариф.
3. Создать тестовый платёж YooKassa.
4. Проверить, что платёж содержит metadata:
   - `order_id`
   - `customer_id`
   - `plan_id`
5. Завершить тестовый платёж.
6. Проверить статус заказа в staging DB.
7. Проверить, что Remnawave создал или продлил пользователя.
8. Проверить, что повторный webhook не создаёт вторую подписку.
9. Искусственно перевести заказ в `PROVISIONING_FAILED` и запустить retry.
10. Проверить, что retry выдал доступ без изменения оплаченного периода.

## Rollback

```bash
cd /opt/alanet/deploy
sudo docker compose -f compose.staging.yml --env-file .env.staging down
```

Данные staging можно удалить только после подтверждения, что там нет нужных тестовых артефактов:

```bash
sudo docker volume rm alanet-staging_billing-staging-data
```
