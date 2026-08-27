# ALANET — Day 24 Rotation Checklist

Дата: 2026-08-27

Цель: подготовить практическую ротацию Telegram, YooKassa и Remnawave без простоя и без потери доступа.

## Общие правила перед стартом

- [ ] Не менять больше одного секрета за один проход.
- [ ] Проверить свежий backup через `/backup`.
- [ ] Проверить общий статус через `/incident`.
- [ ] Убедиться, что есть доступ к prod по SSH.
- [ ] Убедиться, что старый secret не отозван до проверки нового.
- [ ] Не писать значения секретов в Git, документы, Telegram, issue, скриншоты и логи.

## 1. Telegram bot token rotation

Назначение: клиентский бот, admin-команды, уведомления.

### Подготовка

- [ ] Открыть BotFather.
- [ ] Создать новый token для production-бота.
- [ ] Сохранить новый token только в защищённое хранилище.
- [ ] Зафиксировать время начала ротации в change log.

### Переключение

- [ ] Обновить `TELEGRAM_BOT_TOKEN` в production env.
- [ ] При необходимости обновить `TELEGRAM_WEBHOOK_SECRET`.
- [ ] Перезапустить backend/API.
- [ ] Перезапустить worker, если он отправляет Telegram-уведомления.

### Проверка

- [ ] Выполнить `/start` от обычного пользователя.
- [ ] Выполнить `/admin` от admin Telegram ID.
- [ ] Выполнить `/incident`.
- [ ] Проверить, что admin-уведомления доходят.
- [ ] Проверить webhook Telegram.

### Rollback

- [ ] Вернуть старый `TELEGRAM_BOT_TOKEN`.
- [ ] Перезапустить backend/API и worker.
- [ ] Повторить `/admin` и `/incident`.

### Завершение

- [ ] Отозвать старый token только после успешной проверки.
- [ ] Записать дату ротации в secret inventory.

## 2. YooKassa secret key rotation

Назначение: создание платежей, проверка статуса платежа, финансовая сверка.

### Подготовка

- [ ] Проверить, что staging YooKassa test shop работает.
- [ ] Проверить текущий webhook `payment.succeeded`.
- [ ] Создать новый secret key в кабинете YooKassa.
- [ ] Не менять Shop ID без отдельной причины.

### Переключение

- [ ] Обновить `YOOKASSA_SECRET_KEY` в production env.
- [ ] Перезапустить backend/API.
- [ ] Перезапустить worker, если он делает reconciliation или provisioning retry.

### Проверка

- [ ] Создать тестовый checkout в staging.
- [ ] Проверить metadata: `order_id`, `customer_id`, `plan_id`.
- [ ] Провести тестовый payment flow.
- [ ] Проверить webhook `payment.succeeded`.
- [ ] Проверить, что повторный webhook не создаёт вторую подписку.
- [ ] Выполнить `/finance`.
- [ ] Убедиться, что нет `paid but not ACTIVE` и `ACTIVE without succeeded payment`.

### Rollback

- [ ] Вернуть старый `YOOKASSA_SECRET_KEY`.
- [ ] Перезапустить backend/API и worker.
- [ ] Повторить payment status check.

### Завершение

- [ ] Отозвать старый key только после успешной проверки.
- [ ] Записать дату ротации в secret inventory.

## 3. Remnawave API token rotation

Назначение: provisioning, продление, отключение, health-check, registry sync.

### Подготовка

- [ ] Проверить `/incident`.
- [ ] Проверить `/nodes`.
- [ ] Проверить `/ports`.
- [ ] Проверить `/remnawave_sync`.
- [ ] Создать новый Remnawave API token.
- [ ] Не менять squad UUID во время token rotation.

### Переключение

- [ ] Обновить `REMNAWAVE_TOKEN` в production env.
- [ ] Перезапустить backend/API.
- [ ] Перезапустить worker.
- [ ] Перезапустить health-check, если он читает token из env.

### Проверка

- [ ] Проверить `/api/nodes`.
- [ ] Проверить `/api/hosts`.
- [ ] Выполнить `/nodes`.
- [ ] Выполнить `/ports`.
- [ ] Выполнить `/remnawave_sync`.
- [ ] Создать безопасный staging/test provisioning сценарий.
- [ ] Проверить retry provisioning на тестовом заказе или staging-контуре.

### Rollback

- [ ] Вернуть старый `REMNAWAVE_TOKEN`.
- [ ] Перезапустить backend/API, worker и health-check.
- [ ] Повторить `/nodes`, `/ports`, `/remnawave_sync`.

### Завершение

- [ ] Отозвать старый token только после успешной проверки.
- [ ] Записать дату ротации в secret inventory.

## 4. RemnaNode secret rotation

Это отдельная, более рискованная операция. Её нельзя смешивать с ротацией Remnawave API token.

### Правило

- [ ] Делать rolling rotation по одной ноде.
- [ ] Перед изменением каждой shared VPS проверить, что не затрагивается чужой VLESS/проект.
- [ ] После каждой ноды проверять Remnawave connected state и host-port.

### Минимальный порядок

1. Выбрать одну non-critical ноду.
2. Сделать backup node config.
3. Обновить secret только для этой ноды.
4. Перезапустить только RemnaNode container этой ноды.
5. Проверить `/nodes` и `/ports`.
6. Подождать один health-check цикл.
7. Перейти к следующей ноде.

## Итоговый acceptance checklist

- [ ] `/incident` показывает `ok` или понятный controlled warning.
- [ ] `/nodes` видит все активные ноды.
- [ ] `/ports` не показывает закрытые production host-порты.
- [ ] `/finance` не показывает расхождения платежей.
- [ ] `/audit` содержит запись о ротации.
- [ ] Старые секреты отозваны только после подтверждения новых.

