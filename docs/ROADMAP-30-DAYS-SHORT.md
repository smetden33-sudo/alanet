# ALANET — ROADMAP 30 DAYS (short)

Дата: 2026-08-27

| Период | Фокус | Статус | Суть |
|---|---|---|---|
| Day 1–2 | Production baseline + incident mode | ✅ | Зафиксирована текущая prod-схема и один экран диагностики |
| Day 3–7 | Backup, YooKassa, auth, admin MVP | ✅ | Оплата, provisioning и админ-операции работают в основном сценарии |
| Day 8–10 | Telegram + web identity | ✅ | Один клиент = одна карточка, есть защищенная web-сессия |
| Day 11–14 | Admin controls | ✅ | Команды, аудит, подтверждение и retry provisioning |
| Day 15–17 | Subscription lifecycle | 🟡 | Продление и истечение работают, матрица тарифов требует доп. E2E |
| Day 18–20 | Monitoring + registry sync | ✅ | Ноды, порты, incident mode и drift-report под контролем |
| Day 21–23 | Client journey | 🟡 | Публичный checkout и mobile UX еще требуют доводки |
| Day 24–26 | Security + legal | 🟡 | Security checklist подготовлен; юридический контур ждёт реквизиты и тексты |
| Day 27–28 | Failure tests | 🟡 | Матрица отказов и safe smoke runner подготовлены; destructive tests только в окно |
| Day 29–30 | RC + production release | 🟡 | RC и Day 30 checklist подготовлены; коммерческий запуск ждёт legal и real control payment |

## Day 24–30 table

| День | Цель | Артефакт | Ready | Risk |
|---|---|---|---|---|
| 24 | Ротация секретов | `SECRET-INVENTORY.md`, `SECRET-ROTATION-RUNBOOK.md`, `DAY24-ROTATION-CHECKLIST.md` | Подготовлено | Потеря доступа при ошибке |
| 25 | Сетевой и системный hardening | `DAY25-HARDENING-CHECKLIST.md`, firewall, закрытые PostgreSQL/Redis, rate limit | Да | Случайно отрезать рабочий доступ |
| 26 | Юридический контур и retention | `DAY26-LEGAL-READINESS-CHECKLIST.md`, оферта, privacy policy, data deletion process | Ожидает данные | Нет правовой готовности к продажам |
| 27 | Платежные и provisioning-сценарии | `FAILURE-TEST-MATRIX.md`, `infra/scripts/day27_28_failure_smoke.py` | Подготовлено | Двойная выдача или потеря доступа |
| 28 | Отказы инфраструктуры | manual-gated Remnawave/node/rollback scenarios | Подготовлено | Неотработанный failover |
| 29 | Заморозить и подготовить RC | `DAY29-RELEASE-CANDIDATE-CHECKLIST.md`, frozen scope, smoke tests, version pinning | Подготовлено | Непроверенный релиз-кандидат |
| 30 | Выпустить и подтвердить production | `DAY30-PRODUCTION-RELEASE-CHECKLIST.md`, safe control launch, admin commands, daily report | Частично | Коммерческий путь не подтвержден end-to-end |

## Следующий приоритет

1. Дожать security и legal readiness.
2. Провести failure tests.
3. Подготовить RC и production release.
