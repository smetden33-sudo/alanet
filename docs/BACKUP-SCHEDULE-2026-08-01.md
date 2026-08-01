# ALANET — расписание backup prod/head/nodes в S3

Дата внедрения: 01.08.2026  
Контур: production  
Часовой пояс systemd: Europe/Moscow / MSK

## Расписание

Backup выполняется два раза в день:

- 09:00 MSK;
- 18:00 MSK.

Для снижения одновременной нагрузки включён `RandomizedDelaySec=10m`, поэтому фактический старт может быть в пределах 10 минут после указанного времени.

## Production backup

Systemd:

- `alanet-backup.service`
- `alanet-backup.timer`

Что попадает в архив:

- billing PostgreSQL dump;
- Remnawave PostgreSQL dump;
- production `.env`;
- Caddy config;
- Remnawave config;
- node registry;
- Beszel compose/config.

S3 target:

- `alanet/prod/alanet-*.tar.gz.enc`

Status:

- `/var/lib/alanet-monitor/backup.status.json`

Проверенный ручной запуск:

```text
alanet-20260801T104605Z.tar.gz.enc
status=ok
external=uploaded
```

## Node/head backup

Systemd:

- `alanet-node-backup.service`
- `alanet-node-backup.timer`

Источник targets:

- `/opt/alanet/infra/node-registry.json`
- `/opt/alanet/infra/head-registry.json`

SSH key:

- `/etc/alanet/ssh/alanet_deploy_ed25519`
- права: `600`
- владелец: root

Что попадает в архив по каждой ноде:

- `/opt/remnanode`;
- `/opt/remnanode-*`;
- Xray/Sing-box systemd/config paths, если есть;
- Docker metadata;
- network metadata;
- iptables/nft ruleset snapshot;
- systemd services/timers snapshot.

S3 target:

- `alanet/prod/node-backups/alanet-node-backups-*.tar.gz.enc`

Status:

- `/var/lib/alanet-monitor/node-backup.status.json`

Проверенный ручной запуск:

```text
alanet-node-backups-20260801T104542Z.tar.gz.enc
status=ok
ok_count=9
fail_count=0
```

## Head registry

Файл создан:

- `/opt/alanet/infra/head-registry.json`

Сейчас `head-a`, `head-b`, `head-c` имеют статус `pending`, потому что IP/SSH-доступы не были предоставлены/не найдены в production inventory.

Чтобы включить head в расписание, добавить запись:

```json
{
  "name": "head-a",
  "ip": "X.X.X.X",
  "ssh_user": "root",
  "ssh_port": 22,
  "status": "active"
}
```

После этого `alanet-node-backup.service` автоматически начнёт включать head в S3 backup.

## Проверочные команды

```bash
systemctl list-timers --all 'alanet-backup.timer' 'alanet-node-backup.timer'
systemctl start alanet-backup.service
systemctl start alanet-node-backup.service
cat /var/lib/alanet-monitor/backup.status.json
cat /var/lib/alanet-monitor/node-backup.status.json
```

