# ALANET Backup & Restore — Day 4 Report — 2026-07-31

## Цель

Подготовить production backup pipeline к коммерческой эксплуатации:

- ежедневный backup PostgreSQL и конфигураций;
- шифрование перед внешней выгрузкой;
- внешний backup target через S3/rclone/filesystem;
- weekly restore-test;
- machine-readable status для мониторинга и Telegram admin-команд.

## Что внедрено

### 1. Расширен production backup

Файл:

- `infra/deploy/backup-production.sh`

Prod path:

- `/usr/local/sbin/alanet-backup`

Backup по-прежнему создаёт локальный archive:

```text
/var/backups/alanet/alanet-<UTC>.tar.gz
```

В archive входят:

- `remnawave.sql.gz`;
- `billing.sql.gz`;
- `configuration.tar.gz`.

`configuration.tar.gz` теперь включает:

- Remnawave `.env`;
- Remnawave compose;
- Remnawave subscription `.env`;
- Remnawave subscription compose;
- RemnaNode compose;
- ALANET `.env`;
- ALANET compose;
- Caddyfile;
- `infra/node-registry.json`;
- Beszel compose;
- Beszel agent compose.

### 2. Добавлен encrypted external layer

Внешний слой включается только при наличии:

```text
ALANET_BACKUP_ENCRYPTION_PASSPHRASE
```

Это сделано специально: backup содержит `.env` и секреты, поэтому external upload запрещён без шифрования.

Поддерживаются три варианта external target:

| Вариант | Env |
| --- | --- |
| Mounted/external directory | `ALANET_BACKUP_EXTERNAL_DIR` |
| rclone remote | `ALANET_BACKUP_RCLONE_DEST` |
| AWS CLI / S3 URI | `ALANET_BACKUP_S3_URI` |

Encrypted file format:

```text
alanet-<UTC>.tar.gz.enc
```

Шифрование:

```text
openssl enc -aes-256-cbc -pbkdf2 -salt
```

### 3. Добавлен external backup config example

Файл:

- `infra/deploy/external-backup.env.example`

Prod path:

- `/etc/alanet/external-backup.env.example`

Настоящий конфиг должен быть создан вручную:

```bash
sudo install -m 0600 /etc/alanet/external-backup.env.example /etc/alanet/external-backup.env
sudo nano /etc/alanet/external-backup.env
```

Минимально нужно заполнить:

```text
ALANET_BACKUP_ENCRYPTION_PASSPHRASE=<long random passphrase>
ALANET_BACKUP_S3_URI=s3://<bucket>/<prefix>
```

или:

```text
ALANET_BACKUP_ENCRYPTION_PASSPHRASE=<long random passphrase>
ALANET_BACKUP_RCLONE_DEST=<remote>:<bucket>/<prefix>
```

или для mounted storage:

```text
ALANET_BACKUP_ENCRYPTION_PASSPHRASE=<long random passphrase>
ALANET_BACKUP_EXTERNAL_DIR=/mnt/alanet-backups
```

### 4. Restore-test обновлён

Файл:

- `infra/deploy/alanet-restore-test`

Prod path:

- `/usr/local/sbin/alanet-restore-test`

Новая логика:

1. Если настроен `ALANET_BACKUP_EXTERNAL_DIR` и там есть `*.tar.gz.enc`, restore-test берёт external encrypted backup.
2. Расшифровывает его во временную директорию.
3. Извлекает `billing.sql.gz`.
4. Поднимает временный PostgreSQL container.
5. Восстанавливает dump.
6. Проверяет:
   - количество таблиц;
   - customers;
   - orders;
   - subscriptions;
   - payments.
7. Удаляет временный контейнер и временные файлы.

Если external backup не настроен, restore-test работает по локальному archive, как раньше.

### 5. Исправлена flaky readiness проблема restore-test

Причина:

- официальный `postgres:16-alpine` во время init может кратко отвечать на `pg_isready`, затем перезапускается внутри entrypoint;
- старый restore-test иногда ловил эту короткую фазу и падал.

Исправление:

- readiness теперь проверяется через `psql -Atqc "select 1"`;
- требуется две успешные проверки подряд.

### 6. Добавлены status JSON

Backup status:

```text
/var/lib/alanet-monitor/backup.status.json
```

Пример текущего статуса:

```json
{
  "status": "ok",
  "message": "local backup created; external=skipped_no_encryption_passphrase",
  "external_archive": null
}
```

Restore-test status:

```text
/var/lib/alanet-monitor/restore-test.status.json
```

Пример текущего статуса:

```json
{
  "status": "ok",
  "message": "restore test passed",
  "source": "local",
  "tables": 12,
  "customers": 7,
  "orders": 11,
  "subscriptions": 7,
  "payments": 6
}
```

### 7. Systemd обновлён

Unit files:

- `alanet-backup.service`
- `alanet-restore-test.service`

Оба unit теперь читают optional env:

```text
EnvironmentFile=-/etc/alanet/external-backup.env
```

Если файла нет — сервисы работают в локальном режиме.

Timers:

- `alanet-backup.timer` active;
- `alanet-restore-test.timer` active.

## Проверки на prod

### Local backup

Команда:

```bash
sudo /usr/local/sbin/alanet-backup
```

Результат:

```text
Created /var/backups/alanet/alanet-20260731T145918Z.tar.gz external=skipped_no_encryption_passphrase
```

Причина `skipped_no_encryption_passphrase`:

- настоящий external secret ещё не настроен;
- это безопасное ожидаемое поведение.

### Local restore-test

Команда:

```bash
sudo /usr/local/sbin/alanet-restore-test
```

Результат:

```text
restore_test_ok=alanet-20260731T145825Z.tar.gz source=local tables=12 customers=7 orders=11 subscriptions=7 payments=6
```

### External encrypted simulation

Проведён тест через временную external directory:

- создан encrypted `.tar.gz.enc`;
- restore-test восстановил именно `source=external`;
- временная директория удалена после теста.

Результат simulation:

```text
restore_test_ok=alanet-20260731T145825Z.tar.gz.enc source=external tables=12 customers=7 orders=11 subscriptions=7 payments=6
```

### Production health-check

После изменений:

```text
status=ok
```

## Timeweb S3 включён через rclone

2026-07-31 подключён реальный Timeweb Cloud S3-compatible bucket через `rclone`.

Параметры без секретов:

| Параметр | Значение |
| --- | --- |
| Endpoint | `https://s3.twcstorage.ru` |
| Region | `ru:ru-1-hot` |
| Bucket | `e21b4142-5333-417f-ad02-0fef03f91632` |
| Prefix | `alanet/prod` |
| rclone remote | `timeweb:` |

Фактически проверено:

```text
backup.status.json: external=uploaded
external_archive: timeweb:e21b4142-5333-417f-ad02-0fef03f91632/alanet/prod/alanet-20260731T151230Z.tar.gz.enc
restore-test.status.json: source=rclone
tables=12 customers=7 orders=11 subscriptions=7 payments=6
```

Важно: Timeweb вернул `InvalidArgument` при rclone upload с `server_side_encryption=AES256`. Этот header отключён. Backup остаётся зашифрованным клиентским encryption layer:

```text
openssl enc -aes-256-cbc -pbkdf2 -salt
```

## Что осталось после подключения Timeweb

1. Сохранить `ALANET_BACKUP_ENCRYPTION_PASSPHRASE` вне VPS в password manager.
2. Добавить `/backup` вывод `backup.status.json` и `restore-test.status.json`, а не только поиск локального archive.
3. После 2–3 дней стабильной внешней выгрузки уменьшить локальное хранение или перенести Docker builds off-host, чтобы держать диск prod ниже 70–75%.

## Текущий риск после Day 4

| Риск | Статус |
| --- | --- |
| Нет restore-test status | Снят |
| Restore-test flaky на Postgres init | Снят |
| Backup не включает node registry/Beszel config | Снят |
| Внешняя выгрузка без шифрования | Заблокирована by design |
| Реальный S3 ещё не подключён | Остаётся до получения credentials |
| Диск prod 88% | Остаётся; после S3 нужно уменьшить local retention/вынести архивы |
