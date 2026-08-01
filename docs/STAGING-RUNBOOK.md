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
sudo docker exec alanet-caddy-1 caddy validate --config /etc/caddy/Caddyfile
sudo docker exec alanet-caddy-1 caddy reload --config /etc/caddy/Caddyfile
```

## Webhooks

YooKassa:

- event: `payment.succeeded`
- URL: `https://api-staging.alanet.ru/webhooks/yookassa`

Telegram:

- URL: `https://api-staging.alanet.ru/webhooks/telegram`
- secret token должен совпадать с `TELEGRAM_WEBHOOK_SECRET`.

## End-to-end тест

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
