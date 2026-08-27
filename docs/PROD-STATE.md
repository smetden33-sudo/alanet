# ALANET Production State

Дата: 2026-08-27  
Статус: production healthy

## Краткое состояние

| Раздел | Статус | Примечание |
|---|---:|---|
| Prod-сервисы | OK | `web`, `api`, `worker`, `caddy`, `remnawave`, `remnanode`, `beszel`, `beszel-agent` работают |
| Ноды | OK | `13/13 connected` в Remnawave |
| Backup | OK | Prod и node-backup уходят в S3 Timeweb |
| Monitoring | OK | Beszel и ALANET health-check активны |
| CI / deploy | OK | GitHub Actions собирает images и деплоит на prod автоматически |
| Registry / Remnawave | OK | Drift = `0 critical / 0 warnings` |

## Production deploy

- Web image: `ghcr.io/smetden33-sudo/alanet-web:08f4a7771de8f048f9f367e64c1f06ea603e0af2`
- Backend image: `ghcr.io/smetden33-sudo/alanet-backend:08f4a7771de8f048f9f367e64c1f06ea603e0af2`

## Monitoring

- `https://alanet.ru`
- `https://account.alanet.ru`
- `https://api.alanet.ru`
- `https://panel.alanet.ru`
- `https://monitor.alanet.ru`

## Backup

- Local backups: short rollback window only
- Durable backups: S3 Timeweb
- Node backups: enabled
- Restore-test: enabled

## Current risks

| Риск | Статус | Комментарий |
|---|---:|---|
| Shared VPS nodes | Present | Нужна аккуратность: на части хостов есть сторонние сервисы |
| SSH на старый `22` | Present | Для некоторых VPS используется нестандартный порт или внешний фильтр |
| Staging on prod host | Present | Staging-контейнеры живут на том же сервере, но исключены из prod-метрик |
| Disk pressure | Controlled | Следить за `/` и Docker cache, без `--volumes` prune |

## Точка восстановления

1. Проверить `health-check`.
2. Проверить `node-backup.status.json` и `backup.status.json`.
3. Проверить `Remnawave registry sync`.
4. При необходимости откатить images на предыдущий SHA.

## Следующий приоритет

1. Incident mode / admin UX.
2. Staging-hardening для оплат и provisioning.
3. Дальнейшая автоматизация registry/monitoring.
