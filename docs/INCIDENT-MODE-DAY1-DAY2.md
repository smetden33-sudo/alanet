# ALANET — план на Day 1–2 для incident mode

Дата: 2026-08-27  
Статус: baseline и incident mode уже реализованы, документ фиксирует порядок работ и артефакты.

| День | Цель | Артефакт | Ready | Risk |
|---|---|---|---|---|
| 1 | Зафиксировать production baseline: сервисы, ноды, backup, monitoring, CI/deploy и риски | `docs/PROD-STATE.md`, `docs/PROD-STATE-SHORT.md`, `docs/PRODUCTION-RISK-MAP-2026-07-31.md`, `docs/PRODUCTION-ARCHITECTURE.md`, `docs/PRODUCTION-INVENTORY.md` | Да | Скрытые ручные настройки, старые секреты, shared VPS-контуры |
| 2 | Закрепить incident mode и админ-UX: один экран, пороги, follow-up команды, аудит | `/incident`, `/health`, `/ports`, `/backup`, `/disk`, `/cleanup`, `/risk`, `/audit`, `backend/app/telegram.py`, `infra/deploy/verify-production.sh`, `infra/deploy/alanet-prod-ops-collector` | Да | Шумные ложные алерты, расхождение статуса между мониторингом и Telegram, риск перегрузить админа деталями |

## Критерий готовности

- Day 1: у команды есть единая картина production и точка восстановления.
- Day 2: один ` /incident ` показывает, где проблема, а дальше ведёт к правильным follow-up командам.

