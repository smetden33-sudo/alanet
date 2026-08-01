# ALANET Production Risk Map — 2026-07-31

Дата аудита: 2026-07-31  
Время prod: Europe/Moscow, NTP active, clock synchronized  
Prod host: `fin015.vpn-alania.ru`  
Primary VPS: `78.17.54.252`

Документ фиксирует текущее production-состояние ALANET без раскрытия секретов. Секретные значения, токены, пароли и ключи намеренно не записываются.

## 1. Production-схема

### Публичные endpoints

| Endpoint | Назначение | Статус аудита |
| --- | --- | --- |
| `https://alanet.ru` | Основной сайт | `200` |
| `https://account.alanet.ru` | Личный кабинет / клиентский frontend | `200` |
| `https://api.alanet.ru/health` | Backend health endpoint | `200` |
| `https://panel.alanet.ru` | Remnawave panel | `200` |
| `https://sub.alanet.ru` | Remnawave subscription service | `404` на корне, ожидаемо для root |
| `https://monitor.alanet.ru` | Beszel monitoring | `200` |

### Docker services на prod

| Container | Image | Роль | Статус |
| --- | --- | --- | --- |
| `alanet-web-1` | `alanet-web` | Сайт / frontend | Up |
| `alanet-api-1` | `alanet-api` | Backend API | Up |
| `alanet-worker-1` | `alanet-worker` | Фоновые задачи / отчёты / retries | Up |
| `alanet-caddy-1` | `caddy:2.10-alpine` | HTTPS reverse proxy | Up |
| `alanet-billing-db-1` | `postgres:16-alpine` | Billing PostgreSQL | Up, healthy |
| `alanet-billing-redis-1` | `redis:7.4-alpine` | Queue/cache | Up |
| `remnawave` | `remnawave/backend:2` | Remnawave control plane | Up, healthy |
| `remnawave-db` | `postgres:18.4` | Remnawave PostgreSQL | Up, healthy |
| `remnawave-redis` | `valkey/valkey:9-alpine` | Remnawave Redis/Valkey | Up, healthy |
| `remnawave-subscription-page` | `remnawave/subscription-page:latest` | Subscription frontend | Up |
| `remnanode` | `remnawave/node:latest` | Local FIN node on prod | Up |
| `beszel` | `henrygd/beszel:latest` | Monitoring hub | Up |
| `beszel-agent` | `henrygd/beszel-agent:latest` | Prod monitoring agent | Up |

### Caddy routing

| Domain | Backend |
| --- | --- |
| `alanet.ru`, `account.alanet.ru` | ALANET web |
| `api.alanet.ru` | ALANET API |
| `panel.alanet.ru` | Remnawave panel |
| `sub.alanet.ru` | Remnawave subscription service |
| `monitor.alanet.ru`, `beszel.alanet.ru` | Beszel |

### Открытые prod listeners

| Address | Port | Назначение |
| --- | ---: | --- |
| `0.0.0.0` / `[::]` | `80` | HTTP, Caddy |
| `0.0.0.0` / `[::]` | `443` | HTTPS, Caddy |
| `0.0.0.0` / `[::]` | `22` | SSH |
| `*` | `8443` | FIN Xray public host |
| `*` | `2222` | Local RemnaNode control port |
| `127.0.0.1` | `8000` | API internal |
| `127.0.0.1` | `3100` | Web internal |
| `127.0.0.1` | `3000-3001` | Remnawave internal |
| `127.0.0.1` | `3010` | Subscription page internal |
| `127.0.0.1` | `8090` | Beszel internal |
| `127.0.0.1` | `6767` | Remnawave DB exposed locally |

## 2. VPN-ноды

Источник: `infra/node-registry.json`, Remnawave `/api/nodes`, Remnawave `/api/hosts`, Beszel systems.

| Node | Country | IP | Public port | SSH/control port | Remnawave | Host | Beszel |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| `ALANET-FIN-01` | FI | `78.17.54.252` | `8443` | `2222` | connected | active | через `ALANET-PROD` |
| `ALANET-DE-1` | DE | `132.243.228.206` | `2053` | `22` | connected | active | up |
| `ALANET-CZ-1` | CZ | `141.133.172.38` | `2053` | `22` | connected | active | up |
| `ALANET-SE-1` | SE | `89.125.243.225` | `2053` | `22` | connected | active | up |
| `ALANET-PL-1` | PL | `78.17.154.237` | `2053` | `34852` | connected | active | up |
| `ALANET-ES-1` | ES | `78.17.180.246` | `2053` | `22` | connected | active | up |
| `ALANET-LV-1` | LV | `213.155.12.131` | `2053` | `22` | connected | active | up |
| `ALANET-RU-1` | RU | `80.78.245.199` | `2053` | `22` | connected | active | up |
| `ALANET-RU-2` | RU | `195.19.20.123` | `2053` | `22` | connected | active | up |

Сводка:

- Remnawave nodes: `9`
- Remnawave hosts: `9`
- Beszel systems: `9`
- Billing customers: `7`
- Billing orders: `11`
- Billing subscriptions: `7`
- Billing payments: `6`
- Billing audit log records: `17`

## 3. Авторизация и точки доступа

### Telegram bot

| Компонент | Текущее состояние | Риск |
| --- | --- | --- |
| Admin binding | Используется `TELEGRAM_ADMIN_CHAT_ID` | Один админ без ролей |
| Admin commands | `/admin`, `/stats`, `/user`, `/grant`, `/extend`, `/revoke`, `/nodes`, `/orders`, `/health`, `/ports`, `/backup`, `/retry_failed`, `/node`, `/remnawave_sync`, `/payments`, `/finance` | Команды защищены проверкой admin ID, но нет RBAC |
| Confirmation flow | Для опасных действий есть подтверждение через inline callback | Хорошо |
| Audit log | Пишется в БД для ручных admin-действий | Хорошо, но нужен удобный `/audit [дни]` |
| Client identity | Клиентская привязка должна идти по `telegram_id` | Правильная модель; username не должен быть identity |

### Backend/API

| Точка | Текущее состояние | Риск |
| --- | --- | --- |
| Public API | За Caddy, health endpoint доступен | Нужна периодическая проверка auth-sensitive endpoints |
| Rate limit | В коде есть path-level rate limiting для отдельных endpoint | Нужно расширить на auth/payment/provisioning paths |
| YooKassa webhook | Используется отдельный webhook endpoint и secret/config в `.env` | Нужны регулярная сверка платежей и replay/idempotency checks |
| Provisioning retry | Есть retry-механизмы и `/retry_failed` | Хорошо, нужно daily report по failed |

### Remnawave

| Точка | Текущее состояние | Риск |
| --- | --- | --- |
| Panel | `https://panel.alanet.ru`, HTTP `200` | Нужна политика доступа/2FA, если доступно в Remnawave |
| API token | Хранится в `/opt/alanet/deploy/.env` | Нет формального rotation metadata |
| Node secret | Используется RemnaNode secret в контейнерах нод | Нет формального rotation plan |

### YooKassa

| Точка | Текущее состояние | Риск |
| --- | --- | --- |
| Shop ID / secret | Хранятся в `/opt/alanet/deploy/.env` | Нужна процедура rotation и staging separation |
| Notifications | URL: `https://api.alanet.ru/webhooks/yookassa` | Нужно регулярно проверять в кабинете YooKassa |
| Financial reconciliation | Код сверки есть | Нужно убедиться, что включён daily schedule и alerting |

### SSH

| Цель | Текущее состояние | Риск |
| --- | --- | --- |
| Prod | Доступ через deploy key | Хорошо; нужен rotation plan |
| Ноды | Смешанная схема: часть password, часть key-based, разные SSH ports | Высокий риск: нужно перейти на deploy key + отключить password login |

### Beszel

| Точка | Текущее состояние | Риск |
| --- | --- | --- |
| Hub | `https://monitor.alanet.ru`, HTTP `200` | Нужна отдельная политика пароля/2FA, если доступно |
| Agents | 9 систем, все `up` | Хорошо |
| Agent key | Используется общий public key hub | Нужна процедура rotation |

## 4. Реестр секретов без значений

| Secret/config | Где используется | Где хранится | Created/changed | Rotation | Rollback |
| --- | --- | --- | --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Telegram bot, webhook, admin alerts | `/opt/alanet/deploy/.env` | Не зафиксировано | Создать новый token у BotFather, обновить `.env`, redeploy API/worker | Вернуть старый token, если не revoked |
| `TELEGRAM_WEBHOOK_SECRET` | Проверка Telegram webhook | `/opt/alanet/deploy/.env` | Не зафиксировано | Сгенерировать новый, обновить webhook и backend | Вернуть старое значение до удаления |
| `TELEGRAM_ADMIN_CHAT_ID` | Admin commands / notifications | `/opt/alanet/deploy/.env` | Изменён на `6137733861` ранее | Менять через `.env` + restart API/worker | Вернуть предыдущий ID, если известен |
| `DATABASE_URL` | Backend billing DB | `/opt/alanet/deploy/.env` | Не зафиксировано | Сменить DB password, обновить `.env`, restart | Вернуть старый пароль до revoke |
| `BILLING_DB_PASSWORD` | Billing PostgreSQL | `/opt/alanet/deploy/.env`, compose | Не зафиксировано | Плановая смена с maintenance window | DB backup + старый пароль до завершения |
| `REMNAWAVE_TOKEN` | Backend provisioning, health-check, registry sync | `/opt/alanet/deploy/.env` | Не зафиксировано | Выпустить новый API token, проверить `/api/nodes`, переключить | Старый token держать до проверки |
| `REMNAWAVE_SQUAD_ID` | Paid subscriptions provisioning | `/opt/alanet/deploy/.env` | Не зафиксировано | Менять только после проверки squads | Вернуть прежний UUID |
| `REMNAWAVE_TRIAL_SQUAD_ID` | Trial subscriptions provisioning | `/opt/alanet/deploy/.env` | Не зафиксировано | Менять только после проверки trial routing | Вернуть прежний UUID |
| RemnaNode `SECRET_KEY` | Все RemnaNode containers | env/compose на нодах | Не зафиксировано | Новый secret + staged rolling reconnect | Старый secret до полного reconnect |
| `YOOKASSA_SHOP_ID` | Payment creation/status checks | `/opt/alanet/deploy/.env` | Не зафиксировано | Switch test/live через staging-first | Вернуть прежний shop ID |
| `YOOKASSA_SECRET_KEY` | YooKassa API | `/opt/alanet/deploy/.env` | Не зафиксировано | Выпустить новый secret, проверить test payment, revoke old | Старый secret до revoke |
| Beszel admin password | Monitoring login | `/opt/beszel/compose.yml` | Не зафиксировано | Сменить в Beszel, проверить login | Emergency reset через compose/env |
| Beszel agent key | Agents authentication | `/opt/beszel/agent-compose.yml`, ноды | Не зафиксировано | Новый hub key + rolling update agents | Старый key до полного перехода |
| SSH deploy key | Prod access | local/admin machines, prod `authorized_keys` | Не зафиксировано | Добавить новый key, проверить, удалить старый | Старый key до удаления |
| Node SSH passwords | Некоторые shared VPS | вне репозитория / ручной доступ | Не зафиксировано | Перейти на key-only, отключить password login | Оставить аварийный доступ через console провайдера |

## 5. Бэкапы и восстановление

### Текущий backup

Systemd:

- `alanet-backup.timer` активен.
- Последний успешный backup: `2026-07-31 03:30 MSK`.
- Backup path: `/var/backups/alanet/alanet-20260731T002959Z.tar.gz`.
- Retention в скрипте: удаление локальных архивов старше 7 дней.

Состав backup archive:

- Remnawave PostgreSQL dump: `remnawave.sql.gz`
- Billing PostgreSQL dump: `billing.sql.gz`
- Configuration bundle:
  - `/opt/remnawave/.env`
  - `/opt/remnawave/docker-compose.yml`
  - `/opt/remnawave/subscription/.env`
  - `/opt/remnawave/subscription/docker-compose.yml`
  - `/opt/remnanode/docker-compose.yml`
  - `/opt/alanet/deploy/.env`
  - `/opt/alanet/deploy/compose.yml`
  - `/opt/alanet/deploy/Caddyfile`

### Restore-test

Systemd:

- `alanet-restore-test.timer` активен.
- Последний успешный restore-test: `2026-07-30 14:53 MSK`.
- Результат: `restore_test_ok=alanet-20260730T002427Z.tar.gz tables=12 customers=7 orders=11 subscriptions=7 payments=6`.

Риск:

- Перед успешным запуском были две ошибки restore-test. Это не авария, но нужно сохранять последний статус restore-test в отдельный файл и показывать его через `/backup`.
- Бэкапы хранятся на той же VPS. При потере VPS локальный backup будет потерян вместе с prod.

## 6. Health-check

Текущее состояние:

- `alanet-healthcheck.timer` активен.
- Последний health state: `ok`.
- Проверяются:
  - сайт;
  - account;
  - API;
  - panel;
  - TLS certificates;
  - Telegram webhook;
  - Remnawave nodes;
  - Remnawave host ports;
  - subscription validity;
  - HTTPS listener;
  - FIN Xray listener;
  - Docker containers.

Последний полный успешный проход:

- `site=200`
- `account=200`
- `api=200`
- `panel=200`
- `telegram_webhook=200`
- `nodes_checked=9`
- `hosts_checked=9`
- `containers=11/11`
- `status=ok`

Ресурсы в health-check:

- Disk: `88%`
- Memory: `78%`
- Load: `0.65` на 1 CPU

Отдельное наблюдение:

- В `17:33 MSK` был transient `host_port_failed` по Испании `78.17.180.246:2053`, затем следующий проход `17:38 MSK` показал `host_port_ok`. Порог incident mode правильно подавляет одиночные всплески.

## 7. Критичные риски

| Priority | Риск | Почему важно | Рекомендация |
| --- | --- | --- | --- |
| P0 | Backup только локальный на prod | Потеря VPS = потеря backup | Вынести backup в S3-compatible storage с encryption и retention `7/30/90` |
| P0 | Диск prod около `88%` | Риск остановки DB/Docker/Caddy при заполнении | Срочно разгрузить `/`, добавить pruning, вынести backup/archive, увеличить диск |
| P1 | SSH доступ к части нод по паролю | Высокий риск компрометации и ручного хаоса | Перевести ноды на deploy key, отключить password login, зафиксировать аварийный console access |
| P1 | Нет формального secret rotation plan | При утечке сложно быстро и безопасно менять секреты | Создать rotation checklist для Telegram, YooKassa, Remnawave, DB, SSH, Beszel |
| P1 | Admin Telegram auth = один ID без ролей | Нет разделения owner/admin/support/readonly | Внедрить RBAC и `/audit [дни]` |
| P1 | Нет подтверждённого внешнего restore-test | Локальный restore-test есть, но не из внешней копии | После S3 добавить weekly restore-test именно из external backup |
| P2 | Root `https://sub.alanet.ru` отдаёт `404` | Технически нормально, но может выглядеть как ошибка | Добавить понятную landing/health страницу или исключить root из пользовательских ссылок |
| P2 | Remnawave/Beszel tokens без metadata created_at | Непонятен возраст секретов | Вести secret inventory с датой создания/последней ротации |
| P2 | Нет отдельного staging для full payment/provisioning flow | Риск тестов на prod | Довести staging-контур для YooKassa test + mock Remnawave |

## 8. Точка восстановления “как сейчас”

Минимальная recoverable snapshot на момент аудита:

| Компонент | Точка восстановления |
| --- | --- |
| Billing DB | `/var/backups/alanet/alanet-20260731T002959Z.tar.gz`, `billing.sql.gz` |
| Remnawave DB | `/var/backups/alanet/alanet-20260731T002959Z.tar.gz`, `remnawave.sql.gz` |
| ALANET `.env` | Внутри `configuration.tar.gz` последнего backup |
| Caddy config | Внутри `configuration.tar.gz` последнего backup |
| Remnawave config | Внутри `configuration.tar.gz` последнего backup |
| Node registry | `infra/node-registry.json`, прод-копия `/opt/alanet/infra/node-registry.json` |
| Docker compose | `/opt/alanet/deploy/compose.yml`, backup copy в archive |
| Ноды | Восстановление через `infra/node-registry.json` + Remnawave node/host records + Ansible/Terraform pipeline |

Проверенная restore baseline:

- Последний успешный restore-test: `2026-07-30 14:53 MSK`
- Проверенный archive: `alanet-20260730T002427Z.tar.gz`
- Проверенные counts: `tables=12`, `customers=7`, `orders=11`, `subscriptions=7`, `payments=6`

## 9. Рекомендуемые следующие действия

1. Освободить или увеличить диск prod: цель ниже `70%`.
2. Вынести backup во внешнее S3-compatible хранилище.
3. Добавить `/audit [дни]` и RBAC для Telegram admin.
4. Перевести SSH нод на key-only.
5. Добавить secret rotation checklist и дату последней ротации.
6. Сохранять machine-readable статус backup/restore-test для `/backup`.
7. Довести staging-контур оплат и provisioning до регулярного E2E smoke test.
