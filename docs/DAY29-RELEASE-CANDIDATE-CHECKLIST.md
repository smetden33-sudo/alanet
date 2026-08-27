# ALANET — Day 29 Release Candidate Checklist

Дата: 2026-08-27

Цель: заморозить состав релиза, проверить RC и не пустить в production неподготовленные изменения.

## Frozen scope

В RC допускается только:

- bugfix критичного production пути;
- правки документации по текущему release;
- smoke/failure checks;
- безопасные monitoring/admin UX улучшения без изменения схемы данных;
- deploy metadata и version pinning.

В RC не допускается:

- новые тарифы;
- новые платежные сценарии;
- массовая ротация секретов;
- firewall changes на shared VPS;
- RemnaNode secret rotation;
- миграции БД без отдельного rollback;
- включение публичного checkout без юридической готовности.

## RC checklist

| Проверка | Команда/артефакт | Ready | Risk |
|---|---|---|---|
| Clean working tree | `git status --short` | Нет | В релиз попадут черновики |
| Git SHA зафиксирован | commit SHA / image tag | Нет | Непонятно, что откатывать |
| Full backup | `/backup`, `backup.status.json` | Нет | Невозможен rollback |
| Restore-test | `restore-test.status.json` | Нет | Backup может оказаться непригодным |
| Safe failure smoke | `python infra/scripts/day27_28_failure_smoke.py` | Да | Локально может быть skip без backend deps |
| Live readonly smoke | `python infra/scripts/day27_28_failure_smoke.py --live-readonly` | Да | Проверяет доступность, но не payment path |
| Production health | `/incident`, `/health` | Нет | Скрытая деградация перед релизом |
| Remnawave state | `/nodes`, `/ports`, `/remnawave_sync` | Нет | Drift или закрытые host-порты |
| Payment readiness | `/finance`, staging paid-checkout | Нет | Оплата может не активировать подписку |
| Admin readiness | `/admin`, `/audit`, `/retry_failed` | Нет | Нет ручного recovery при сбое |
| Deploy workflow | GitHub Actions build/deploy | Нет | Неизвестен результат автодеплоя |

## Local/CI pre-RC commands

```bash
python infra/scripts/day27_28_failure_smoke.py
python infra/scripts/day27_28_failure_smoke.py --live-readonly
npm test
```

Если backend dependencies установлены:

```bash
cd backend
python -m unittest backend.tests.test_payment_metadata
python ../infra/scripts/day27_28_failure_smoke.py
```

## Production pre-RC commands

Через Telegram admin:

```text
/incident
/health
/ports
/backup
/disk
/finance
/audit 1
/remnawave_sync
```

Через SSH на prod:

```bash
sudo systemctl start alanet-healthcheck.service
sudo cat /var/lib/alanet-monitor/health.state
sudo cat /var/lib/alanet-monitor/health.status.json
sudo cat /var/lib/alanet-monitor/backup.status.json
sudo cat /var/lib/alanet-monitor/restore-test.status.json
sudo docker compose ps
```

## No-go criteria

RC нельзя выпускать, если:

- `/incident` показывает `incident`;
- свежий backup отсутствует;
- restore-test не проходил;
- `/ports` показывает закрытый production host-port;
- `/finance` показывает расхождения payment/subscription;
- есть непонятый `PROVISIONING_FAILED`;
- staging paid-checkout не проходит;
- рабочее дерево содержит незапланированные файлы;
- юридический контур требуется для публичного checkout, но не готов.

## Rollback checklist

- [ ] Зафиксирован предыдущий working image SHA.
- [ ] Известна команда возврата `ALANET_WEB_IMAGE` и `ALANET_BACKEND_IMAGE`.
- [ ] Есть свежий backup БД и конфигурации.
- [ ] Есть доступ к prod SSH.
- [ ] Есть Telegram admin канал для уведомлений.
- [ ] После rollback выполняются `/incident`, `/health`, `/ports`.

## Acceptance

- [ ] Scope frozen.
- [ ] RC commit SHA известен.
- [ ] Safe smoke прошёл.
- [ ] Live readonly smoke прошёл.
- [ ] Prod health green или controlled warning.
- [ ] Backup и restore-test подтверждены.
- [ ] Manual recovery команды доступны.

