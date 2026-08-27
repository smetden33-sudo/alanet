# ALANET — Day 30 Production Release Checklist

Дата: 2026-08-27

Цель: подтвердить production release и коммерческий путь перед реальными продажами.

## Release scope

В Day 30 входит:

- выпуск production build;
- проверка public endpoints;
- проверка Telegram admin tools;
- проверка backup/restore readiness;
- проверка Remnawave/node state;
- контроль payment/provisioning path;
- финальный report и backlog второго месяца.

## Production release checklist

| Проверка | Артефакт/команда | Ready | Risk |
|---|---|---|---|
| Release SHA зафиксирован | `git rev-parse --short HEAD` | Да | Непонятный rollback target |
| Working tree clean для релиза | `git status --short` | Нет | Есть незакоммиченные docs/runner изменения |
| Public endpoints smoke | `python infra/scripts/day27_28_failure_smoke.py --live-readonly` | Да | Не проверяет оплату |
| Production health | `/incident`, `/health` | Ожидает ручной проверки | Скрытый incident |
| Remnawave nodes/hosts | `/nodes`, `/ports`, `/remnawave_sync` | Ожидает ручной проверки | Drift или закрытый host-port |
| Backup readiness | `/backup`, restore-test status | Ожидает ручной проверки | Непроверенный rollback |
| Disk readiness | `/disk` | Ожидает ручной проверки | Диск может сорвать deploy/logs/backup |
| Payment path | staging paid-checkout + production readiness | Частично | Реальный платеж не выполнен |
| Real control payment | минимальный тариф реальной картой | Нет | Без него коммерческий путь не подтвержден полностью |
| Admin recovery | `/audit`, `/retry_failed`, `/finance` | Ожидает ручной проверки | Нет быстрого recovery |
| Month-2 backlog | `ROADMAP-MONTH-2.md` | Да | Следующий цикл не приоритизирован |

## Safe control launch result

Команда:

```bash
python infra/scripts/day27_28_failure_smoke.py --live-readonly
```

Результат:

| Endpoint | Expected | Result |
|---|---:|---:|
| `https://alanet.ru` | 200 | 200 |
| `https://account.alanet.ru` | 200 | 200 |
| `https://api.alanet.ru/health` | 200 | 200 |
| `https://panel.alanet.ru` | 200 | 200 |
| `https://sub.alanet.ru` | 404 | 404 |

Итог: safe control launch `OK`.

## No-go criteria

Production release нельзя считать коммерчески завершённым, если:

- нет чистого release commit;
- есть незакоммиченные изменения, которые должны попасть в релиз;
- не подтвержден свежий backup;
- не подтвержден restore-test;
- `/incident` показывает incident;
- `/ports` показывает закрытые production host-порты;
- `/finance` показывает payment/subscription drift;
- не проведен staging paid-checkout;
- публичный checkout требует юридических документов, но они не готовы;
- не выполнен контрольный реальный платеж, если цель — начать реальные продажи.

## Rollback

Минимальный rollback должен содержать:

1. предыдущий image SHA;
2. свежий backup БД и конфигурации;
3. доступ к prod SSH;
4. проверку `/incident` после отката;
5. запись результата в change log.

## Итоговый статус Day 30

| Блок | Статус | Комментарий |
|---|---|---|
| Technical release readiness | Подготовлено | Safe checks зелёные |
| Commercial release readiness | Частично | Нужны legal docs и real control payment |
| Production control launch | OK | Read-only публичные endpoints отвечают |
| Full production release | Не закрыт | Нужен чистый commit/deploy и ручные admin checks |

