# Тихая сеть — MVP на Remnawave

Готовый каркас сервиса подписки: публичный сайт и checkout, FastAPI-биллинг, YooKassa, Telegram webhook, адаптер Remnawave v3, PostgreSQL, Redis/Celery, Caddy и Docker Compose.

> Важно: юридические страницы содержат явно отмеченные шаблоны. Не принимайте реальные платежи до проверки оферты, политики данных, возвратов, чеков и применимого законодательства профильным юристом.

## Что уже реализовано

- адаптивный русскоязычный сайт, тарифы и форма заказа;
- создание заказа и платежа YooKassa с сохранённым ключом идемпотентности;
- повторная проверка платежа через API YooKassa при webhook;
- защита от повторной выдачи доступа;
- provisioning пользователя и продление в Remnawave;
- корректное продление от действующей даты окончания, а для истёкшей подписки — от текущего времени;
- хранение числового `remnawave_user_id` для Remnawave v3 и legacy UUID только для совместимости;
- webhook Telegram с проверкой secret token;
- retry/reconciliation entry points, метрики, healthcheck;
- изолированная сеть для PostgreSQL и Redis;
- reverse proxy и security headers в Caddy.

## Локальный запуск сайта

```powershell
npm.cmd install
npm.cmd run dev
```

Сайт откроется на `http://localhost:3000`.

## Запуск backend

1. Скопируйте `.env.example` в `.env`.
2. Замените все демонстрационные значения и заполните токены.
3. Запустите:

```powershell
docker compose up --build
```

API: `http://localhost:8000`, healthcheck: `/health`, документация в development: `/api/docs`.

## Обязательные настройки перед staging

1. В Remnawave создайте отдельный API token только для billing backend и Internal Squad.
2. Укажите `REMNAWAVE_BASE_URL`, `REMNAWAVE_TOKEN`, `REMNAWAVE_SQUAD_ID`.
3. В YooKassa заполните shop ID, secret key, VAT code и настройте `payment.succeeded` на `https://api.example.com/webhooks/yookassa`.
4. Для Telegram задайте webhook на `https://api.example.com/webhooks/telegram` с тем же secret token, что в `.env`.
5. Замените домены, email, ссылку поддержки и secret login route Caddy.
6. Включите MFA/Passkey в Remnawave Panel и ограничьте Panel по IP или identity-aware proxy.
7. Node Port разрешите только со стороны Panel. PostgreSQL и Redis не публикуйте.
8. Закрепите конкретные версии Remnawave Panel/Node и прогоните contract test адаптера перед обновлением.

## Принцип обработки оплаты

`CREATED → PAYMENT_PENDING → PROVISIONING → ACTIVE`

Webhook не считается доказательством оплаты сам по себе: backend извлекает payment ID, запрашивает объект платежа у YooKassa и сверяет статус, сумму, RUB и `metadata.order_id`. Если Remnawave недоступен, заказ становится `PROVISIONING_FAILED`; повторная задача должна искать пользователя по стабильному username, поэтому второй VPN-пользователь не создаётся.

## Ограничения текущего каркаса

- задачи Celery для retry и reconciliation оставлены безопасными entry points — подключите выборку заказов, алерты и политику повторов под вашу эксплуатацию;
- одноразовый bind-token Telegram обозначен в UX, но таблица и полноценный bind flow должны быть добавлены перед публичным запуском;
- шаблоны юридических документов требуют реальных реквизитов и проверки;
- Caddy ожидает, что контейнеры Remnawave и Subscription Page подключены к сети `edge`, либо upstream заменён на доступный внутренний адрес;
- subscription URL является секретом: не добавляйте его в логи, аналитику и сообщения об ошибках.

## Проверки

```powershell
npm.cmd run build
python -m pytest backend/tests
docker compose config
```

Для staging отдельно проверьте: повторный webhook, двойной клик оплаты, сбой Remnawave после успешного платежа, продление активной и истёкшей подписки, возврат и восстановление базы из внешней копии.
