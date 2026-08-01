# ALANET Timeweb Cloud backup via rclone — 2026-07-31

## Что уже подготовлено

На production установлен `rclone`.

Профиль Cyberduck подтвердил параметры Timeweb Cloud S3:

| Параметр | Значение |
| --- | --- |
| Protocol | `s3` |
| Endpoint | `https://s3.twcstorage.ru` |
| Region | `ru:ru-1-hot` |
| Port | `443` |
| Access field | `Access Key` |
| Secret field | `Secret Access Key` |

На prod создан шаблон:

```text
/etc/alanet/rclone-timeweb.conf.example
```

В репозитории:

```text
infra/deploy/rclone-timeweb.conf.example
infra/deploy/external-backup.env.example
```

## Что нужно получить в Timeweb

1. Bucket name.
2. Access Key.
3. Secret Access Key.
4. Длинная backup encryption passphrase.

Passphrase нужно сохранить отдельно в password manager. Без неё encrypted backup нельзя восстановить.

## Настройка rclone на prod

Создать конфиг:

```bash
sudo install -m 0600 /etc/alanet/rclone-timeweb.conf.example /etc/alanet/rclone.conf
sudo nano /etc/alanet/rclone.conf
```

Заполнить:

```ini
[timeweb]
type = s3
provider = Other
env_auth = false
access_key_id = <TIMEWEB_ACCESS_KEY>
secret_access_key = <TIMEWEB_SECRET_ACCESS_KEY>
endpoint = https://s3.twcstorage.ru
region = ru:ru-1-hot
```

Примечание: не добавлять `server_side_encryption = AES256` для текущего Timeweb remote. Реальный upload вернул `InvalidArgument` с этим header. ALANET уже шифрует backup клиентским `openssl enc -aes-256-cbc -pbkdf2`, поэтому server-side encryption header не нужен.

Проверить bucket:

```bash
sudo RCLONE_CONFIG=/etc/alanet/rclone.conf rclone lsd timeweb:
sudo RCLONE_CONFIG=/etc/alanet/rclone.conf rclone mkdir timeweb:<bucket>/alanet/prod
sudo RCLONE_CONFIG=/etc/alanet/rclone.conf rclone ls timeweb:<bucket>/alanet/prod
```

## Настройка ALANET external backup

Создать env:

```bash
sudo install -m 0600 /etc/alanet/external-backup.env.example /etc/alanet/external-backup.env
sudo nano /etc/alanet/external-backup.env
```

Заполнить:

```env
ALANET_BACKUP_ENCRYPTION_PASSPHRASE=<long-random-passphrase>
ALANET_LOCAL_RETENTION_DAYS=7
ALANET_EXTERNAL_RETENTION_DAYS=90
ALANET_BACKUP_RCLONE_DEST=timeweb:<bucket>/alanet/prod
RCLONE_CONFIG=/etc/alanet/rclone.conf
ALANET_BACKUP_DIR=/var/backups/alanet
ALANET_MONITOR_DIR=/var/lib/alanet-monitor
ALANET_DEPLOY_ENV=/opt/alanet/deploy/.env
```

## Проверка

Запустить backup:

```bash
sudo systemctl start alanet-backup.service
sudo cat /var/lib/alanet-monitor/backup.status.json
```

Ожидаемо:

```text
status=ok
message contains external=uploaded
external_archive starts with timeweb:<bucket>/alanet/prod/
```

Проверить файл в Timeweb:

```bash
sudo RCLONE_CONFIG=/etc/alanet/rclone.conf rclone ls timeweb:<bucket>/alanet/prod
```

Запустить restore-test из внешней копии:

```bash
sudo systemctl start alanet-restore-test.service
sudo cat /var/lib/alanet-monitor/restore-test.status.json
```

Ожидаемо:

```text
status=ok
source=rclone
tables > 0
customers >= 0
orders >= 0
subscriptions >= 0
payments >= 0
```

Фактически проверенный результат 2026-07-31:

```text
backup: external=uploaded
restore-test: source=rclone, tables=12, customers=7, orders=11, subscriptions=7, payments=6
```

## Rollback

Если внешний backup ломается, но локальный backup нужен срочно:

```bash
sudo mv /etc/alanet/external-backup.env /etc/alanet/external-backup.env.disabled
sudo systemctl daemon-reload
sudo systemctl start alanet-backup.service
sudo cat /var/lib/alanet-monitor/backup.status.json
```

В этом режиме backup снова станет локальным:

```text
external=skipped_no_encryption_passphrase
```

## Важное

- Не отправлять `.tar.gz` во внешний storage без encryption passphrase.
- Не хранить Timeweb secret key в Git.
- Не публиковать backup passphrase в Telegram.
- После включения Timeweb backup уменьшить нагрузку на prod disk: проверить retention и свободное место.
