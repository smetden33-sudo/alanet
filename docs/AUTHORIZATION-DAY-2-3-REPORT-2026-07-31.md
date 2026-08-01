# ALANET Authorization — Day 2–3 Report — 2026-07-31

## Цель

Усилить авторизацию ALANET перед масштабированием: отделить роли администраторов, сохранить текущий owner-доступ, добавить удобный audit view и зафиксировать правильную клиентскую identity-модель через Telegram ID.

## Что внедрено

### 1. Telegram admin RBAC

Добавлена ролевая модель без миграции БД. Роли задаются через env-переменные:

| Env | Роль | Назначение |
| --- | --- | --- |
| `TELEGRAM_OWNER_IDS` | `owner` | Полный доступ, включая отзыв подписки |
| `TELEGRAM_ADMIN_IDS` | `admin` | Операции provisioning, billing, ops |
| `TELEGRAM_SUPPORT_IDS` | `support` | Просмотр и audit |
| `TELEGRAM_READONLY_IDS` | `readonly` | Только чтение |
| `TELEGRAM_ADMIN_CHAT_ID` | `owner` fallback | Совместимость со старой схемой |

Текущий `TELEGRAM_ADMIN_CHAT_ID` автоматически считается `owner`, поэтому существующий доступ администратора не ломается.

### 2. Permissions

| Permission | Кто имеет | Команды |
| --- | --- | --- |
| `read` | readonly/support/admin/owner | `/admin`, `/stats`, `/user`, `/nodes`, `/orders`, `/health`, `/ports`, `/backup`, `/node` |
| `audit` | support/admin/owner | `/audit [дни]` |
| `billing` | admin/owner | `/payments`, `/finance` |
| `provision` | admin/owner | `/grant`, `/extend`, `/retry`, `/retry_failed` |
| `ops` | admin/owner | `/remnawave_sync` |
| `revoke` | owner | `/revoke` |

### 3. Защита confirmation flow

Опасные действия теперь проверяются дважды:

1. на этапе создания pending admin action;
2. на этапе inline callback `Подтвердить`.

Для admin actions используется mapping:

| Action | Required permission |
| --- | --- |
| `grant` | `provision` |
| `extend` | `provision` |
| `revoke` | `revoke` |

Если прав не хватает, действие переводится в `DENIED`, а отказ записывается в `audit_log`.

### 4. Команда `/audit [дни]`

Добавлена команда:

```text
/audit [дни]
```

Показывает последние записи audit log:

- timestamp;
- actor;
- action;
- entity;
- target;
- result;
- error.

Ограничения:

- период: 1–90 дней;
- вывод: последние 30 записей;
- длинные ответы автоматически режутся на несколько Telegram-сообщений.

### 5. Client identity model

Проверена текущая модель клиента:

- основной идентификатор клиента в ALANET — `telegram_id`;
- `telegram_username` используется только как отображаемое имя;
- если покупка идёт из Telegram bot, checkout создаётся с `telegram_id`;
- если покупка была web-first, используется bind token для привязки Telegram;
- web session хранится через `WebSession` + HttpOnly cookie;
- session exchange идёт через одноразовый `WebLoginToken`.

Это правильная модель. Username менять нельзя использовать как identity, потому что пользователь Telegram может сменить username.

## Что изменено в коде

Файлы:

- `backend/app/config.py`
- `backend/app/telegram.py`
- `.env.example`

## Проверки

Локально:

```text
python -m py_compile backend/app/config.py backend/app/telegram.py backend/app/main.py backend/app/services.py
```

Результат: ok.

Prod:

- backend `api` rebuilt and restarted;
- `worker` rebuilt and restarted;
- `http://127.0.0.1:8000/health` вернул `{"status":"ok"}`;
- импорт RBAC функций в контейнере успешный;
- текущий admin ID распознан как `owner`;
- owner имеет permission `revoke`;
- production health-check: `status=ok`.

## Что осталось для полного Дня 3

Текущий фундамент web-session уже есть, но для полноценной страницы “Моя подписка” ещё нужно:

1. Улучшить UI личного кабинета:
   - тариф;
   - дата окончания;
   - статус;
   - QR/link;
   - доступные локации;
   - история оплат.
2. Добавить явный Telegram Login/WebApp entrypoint на сайте.
3. Добавить CSRF token для state-changing web actions.
4. Добавить session activity audit:
   - login;
   - logout;
   - failed session exchange.
5. Добавить rate limits на все auth-sensitive endpoints.

## Риск после внедрения

| Риск | Статус |
| --- | --- |
| Потеря старого admin-доступа | Снят: `TELEGRAM_ADMIN_CHAT_ID` остаётся owner fallback |
| Support случайно отзовёт подписку | Снят: `/revoke` только `owner` |
| Admin callback обойдёт права | Снижен: callback и executor проверяют permission |
| Нет видимого audit в Telegram | Снят базово: добавлен `/audit [дни]` |

