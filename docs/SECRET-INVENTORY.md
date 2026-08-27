# ALANET — Secret Inventory

Дата: 2026-08-27

Цель: знать, какие секреты существуют, где они живут, кто их меняет и как откатывать ротацию без потери доступа.

## Правила

- Здесь не хранить сами значения секретов.
- Если секрет уже попал в Git, лог, скриншот или чат, считать его скомпрометированным.
- Перед удалением старого секрета всегда должен быть проверен новый.

## Inventory

| Secret | Used by | Storage | Owner | Rotation trigger | Rollback |
|---|---|---|---|---|---|
| Telegram bot token | Bot API, admin alerts, webhook auth | production `.env` | Bot owner | компрометация, регулярная ротация | вернуть старый token до revoke |
| Telegram webhook secret | Telegram webhook verification | production `.env` | Backend | компрометация, webhook mismatch | вернуть старое значение до удаления |
| Telegram admin chat ID | Admin alerts | production `.env` | Ops | смена администратора | восстановить предыдущий ID |
| Billing DB password | PostgreSQL billing DB | production `.env` + DB role | Backend/DBA | плановая ротация, инцидент | вернуть старый пароль после health-check |
| DATABASE_URL | API/worker DB access | production `.env` | Backend | смена DB credentials | revert `.env` + DB password |
| Remnawave API token | provisioning, registry sync, health-check | production `.env` | Backend/Ops | provider rotation, подозрение на утечку | restore old token until reconnect verified |
| Remnawave squad IDs | paid/trial routing | production `.env` | Backend/Ops | смена squad routing | вернуть прежние UUID |
| RemnaNode secret key | node containers | node env / compose | Node ops | rolling reconnect | keep old secret until all nodes reconnect |
| YooKassa shop ID | payment creation / status checks | production `.env` | Billing | provider-side change | revert shop ID mapping |
| YooKassa secret key | payment API, webhook checks | production `.env` | Billing | provider-side rotation | restore old key until test payment passes |
| Beszel admin password | monitoring login | Beszel config | Ops | compromise, periodic hardening | emergency reset via config |
| Beszel agent key | agent auth | Beszel agent config + nodes | Ops | hub rotation | keep old key until all agents reconnect |
| SSH deploy key | prod deploy access | local admin key + `authorized_keys` | Ops | periodic rotation, compromise | keep old key until verified new key works |
| Node SSH passwords | legacy/shared VPS access | provider/secret storage | Ops | migration to key-only | keep emergency console access |
| S3/rclone credentials | external backup upload | backup env / rclone config | Ops | cloud rotation, compromise | old key until upload verified |
| Backup encryption passphrase | encrypted backup archive | external-backup env | Ops | policy rotation | decrypt verification before switch |

## Priority order

1. Telegram bot token.
2. YooKassa secret key.
3. Remnawave API token and RemnaNode secret.
4. Billing DB password.
5. SSH deploy key.
6. Beszel credentials.
7. Backup and S3 credentials.

