# ALANET — Secret Rotation Runbook

Дата: 2026-08-27

Цель: менять секреты по одному, без потери доступа, с проверкой и понятным rollback.

## Общий порядок

Для любого секрета:

1. Создать новый secret у поставщика или локально.
2. Внести его в защищённое хранилище / encrypted env.
3. Обновить только зависимый сервис.
4. Проверить health-check / webhook / login / payment / provisioning.
5. Убедиться, что новый secret работает параллельно.
6. Только после этого отозвать старый secret.
7. Зафиксировать дату, проверку и результат в audit log / change log.

Если любой шаг не прошёл, не отзывать старый secret.

## Порядок ротации по приоритету

### 1. Telegram bot token

Критично, потому что это клиентские и admin-уведомления.

Шаги:

1. Создать новый token в BotFather.
2. Обновить `TELEGRAM_BOT_TOKEN` в production env.
3. Перезапустить backend/worker.
4. Проверить `/admin` и тестовое уведомление.
5. Проверить incoming webhook / bot polling.
6. Отозвать старый token только после успешной проверки.

Rollback:

- вернуть старый token в env;
- перезапустить сервис;
- проверить доставку сообщений.

### 2. YooKassa secret key

Критично для оплаты и webhook.

Шаги:

1. Выпустить новый secret в YooKassa.
2. Обновить `YOOKASSA_SECRET_KEY`.
3. Проверить тестовый платеж и webhook `payment.succeeded`.
4. Проверить finance reconciliation / metadata checks.
5. После успешного теста отозвать старый secret.

Rollback:

- вернуть предыдущий secret;
- повторить тестовый платеж в staging или test shop.

### 3. Remnawave API token / RemnaNode secret

Критично для provisioning и node sync.

Шаги:

1. Создать новый token / secret.
2. Обновить backend `.env` или node env.
3. Проверить `/api/nodes`, `/api/hosts` и provisioning retry.
4. Проверить registry sync и drift report.
5. Подтвердить reconnect всех затронутых nodes.
6. Удалить старый secret только после полного подтверждения.

Rollback:

- вернуть старый token;
- при необходимости остановить write-sync и оставить report-only режим.

### 4. Billing DB password / DATABASE_URL

Критично для биллинга.

Шаги:

1. Создать новый DB password.
2. Обновить PostgreSQL role/password.
3. Обновить `DATABASE_URL` и dependent envs.
4. Restart API, worker, admin jobs.
5. Проверить `/health`, `/stats`, `/audit`, `/orders`.
6. Убедиться, что billing queries и provisioning работают.
7. Отозвать старый пароль.

Rollback:

- вернуть старый пароль до revoke;
- восстановить соединение сервисов;
- проверить backup перед дальнейшими шагами.

### 5. SSH deploy key

Критично для deploy access.

Шаги:

1. Сгенерировать новый key.
2. Добавить public key на prod в `authorized_keys`.
3. Проверить новый вход второй независимой сессией.
4. Обновить CI / deploy host key usage.
5. Удалить старый key только после проверки.

Rollback:

- вернуть старый key в `authorized_keys`;
- проверить, что доступ не потерян.

### 6. Beszel credentials

Важно для observability, но не для payment path.

Шаги:

1. Обновить admin password / agent key.
2. Переподключить agents.
3. Проверить состояние hub и all agents.
4. Убедиться, что алерты продолжают приходить.

Rollback:

- вернуть старое значение;
- проверить, что агенты снова online.

### 7. Backup / S3 / encryption credentials

Критично для восстановления.

Шаги:

1. Создать новый key / passphrase.
2. Обновить backup env и rclone config.
3. Сделать тестовый encrypted backup upload.
4. Проверить object presence и restore-test.
5. После успешной проверки отозвать старый key.

Rollback:

- вернуть старые credentials;
- повторить backup upload;
- не удалять local rollback buffer до подтверждения restore.

## Минимальный maintenance window checklist

- [ ] Свежий backup сделан и проверен.
- [ ] Есть второй verified admin session.
- [ ] Есть план rollback для конкретного секрета.
- [ ] Есть тест после переключения.
- [ ] Старый secret не удаляется до успешной проверки.

## Запрещено

- Менять несколько критичных секретов одновременно.
- Отзывать старый secret до проверки нового.
- Хранить новые секреты в Git, чатах или скриншотах.
- Проводить ротацию без rollback-плана.

