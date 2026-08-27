# ALANET — Day 24–30 Readiness Report

Дата: 2026-08-27

## Сводка

| День | Блок | Статус | Что сделано | Что осталось |
|---|---|---|---|---|
| 24 | Secrets rotation | Подготовлено | `SECRET-INVENTORY.md`, `SECRET-ROTATION-RUNBOOK.md`, `DAY24-ROTATION-CHECKLIST.md` | Получить новые секреты и окно работ |
| 25 | Network/system hardening | Подготовлено | `DAY25-HARDENING-CHECKLIST.md`, проверена текущая модель ports/rate-limit | Выполнить ручную проверку на prod через SSH/admin |
| 26 | Legal readiness | Ожидает данные | `DAY26-LEGAL-READINESS-CHECKLIST.md` | Реквизиты продавца, оферта, privacy policy, refund rules |
| 27 | Payment/provisioning failure tests | Подготовлено | `FAILURE-TEST-MATRIX.md`, safe runner | Staging paid-checkout и manual payment scenarios |
| 28 | Infrastructure failure tests | Подготовлено | manual-gated сценарии описаны | Окно для Remnawave/node/rollback tests |
| 29 | Release Candidate | Подготовлено | `DAY29-RELEASE-CANDIDATE-CHECKLIST.md`, frozen scope | Чистый release commit, backup/restore/admin checks |
| 30 | Production release | Частично | `DAY30-PRODUCTION-RELEASE-CHECKLIST.md`, safe control launch OK | Real control payment и юридическое разрешение на public checkout |

## Выполненный safe control launch

Проверены публичные endpoints:

| Endpoint | Expected | Result |
|---|---:|---:|
| `https://alanet.ru` | 200 | 200 |
| `https://account.alanet.ru` | 200 | 200 |
| `https://api.alanet.ru/health` | 200 | 200 |
| `https://panel.alanet.ru` | 200 | 200 |
| `https://sub.alanet.ru` | 404 | 404 |

Итог: `OK`.

## Главные блокеры

1. Нужны юридические реквизиты и тексты перед публичным checkout.
2. Нужен real control payment для полного коммерческого подтверждения.
3. Нужен чистый release commit/deploy для фиксации RC.
4. Нужны новые секреты и отдельное окно для фактической ротации.
5. Destructive failure tests можно проводить только в отдельное окно.

## Рекомендованный следующий шаг

Сначала зафиксировать текущие docs/runner изменения отдельным commit, затем выполнить RC gate:

1. `/incident`
2. `/backup`
3. `/disk`
4. `/ports`
5. `/finance`
6. staging paid-checkout
7. production release decision

