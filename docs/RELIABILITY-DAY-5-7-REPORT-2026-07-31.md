# ALANET — отчёт Day 5–7: безотказоустойчивость, эксплуатация, контроль восстановления

Дата: 31.07.2026  
Контур: production  
Основной сервер: 78.17.54.252  

## Цель этапа

Довести MVP до более предсказуемой эксплуатационной модели: администратор должен видеть состояние сервиса, backup, restore-test и ключевых prod-компонентов без ручного SSH-разбора.

## Что выполнено

### 1. Видимость backup/restore в Telegram-админке

Команда `/backup` теперь читает machine-readable статусы:

- `/var/lib/alanet-monitor/backup.status.json`;
- `/var/lib/alanet-monitor/restore-test.status.json`.

Команда показывает:

- свежесть backup;
- результат внешней выгрузки;
- источник restore-test;
- имя архива;
- количество восстановленных таблиц и ключевых сущностей.

Проверенный prod-результат:

```text
Backup: ok, external=uploaded
Restore-test: ok, source=rclone
tables=12, customers=7, orders=11, subscriptions=7, payments=6
```

### 2. Видимость backup/restore в `/health`

Команда `/health` теперь включает строки backup и restore-test, чтобы одна диагностика покрывала не только сайт/API/Remnawave, но и восстановимость.

### 3. Daily audit report усилен backup/restore-сводкой

Ежедневный отчёт администратору теперь дополнительно включает:

- состояние последнего backup;
- наличие внешней копии;
- состояние последнего restore-test;
- источник restore-test;
- количество восстановленных записей.

### 4. Контейнеры API/worker получили read-only доступ к статусам

В `deploy/compose.yml` добавлены read-only mounts:

- `/var/lib/alanet-monitor:/var/lib/alanet-monitor:ro`;
- `/var/backups/alanet:/var/backups/alanet:ro`.

Это позволяет API/worker видеть эксплуатационные статусы без доступа на запись.

### 5. Исправлены права status-файлов

Обнаружено, что backup/restore status JSON создавались с правами `600`, поэтому контейнерный пользователь не мог их читать.

Исправлено:

- status-файлы создаются с `644`;
- каталог `/var/lib/alanet-monitor` доступен на чтение/traverse;
- секреты и приватные конфиги не раскрывались.

### 6. Проверен production после деплоя

Проверено:

- API health: `{"status":"ok"}`;
- `https://alanet.ru/`: HTTP 200;
- `https://account.alanet.ru/`: HTTP 200;
- `https://api.alanet.ru/health`: HTTP 200;
- `alanet-healthcheck.service`: exit 0;
- `/var/lib/alanet-monitor/health.summary`: `status=ok`;
- Docker контейнеры API/worker/web/db/redis/caddy: running;
- timers:
  - `alanet-healthcheck.timer`;
  - `alanet-backup.timer`;
  - `alanet-restore-test.timer`;
  - `alanet-docker-prune.timer`.

## Изменённые файлы

- `backend/app/telegram.py`
- `backend/app/worker.py`
- `deploy/compose.yml`
- `infra/deploy/backup-production.sh`
- `infra/deploy/alanet-restore-test`

## Rollback

Перед заменой prod-файлов сохранены резервные копии:

- `/opt/alanet/backups/day5-7-20260731T152228Z`
- `/opt/alanet/backups/day5-7-scripts-20260731T152410Z`

Rollback:

1. вернуть файлы из соответствующей папки backup;
2. переключить `ALANET_BACKEND_IMAGE` на предыдущий SHA-tag;
3. выполнить `docker compose pull api worker`;
4. выполнить `docker compose up -d api worker`;
4. проверить `curl http://127.0.0.1:8000/health`;
5. запустить `systemctl start alanet-healthcheck.service`.

## Текущие риски

- Диск prod всё ещё занят примерно на 84%; это рабочее состояние, но для роста проекта нужно расширение/разгрузка.
- Внешние backup уже включены, но желательно добавить S3 lifecycle/retention на стороне провайдера.
- Restore-test еженедельный; для активной фазы продаж можно временно запускать чаще после крупных релизов.
