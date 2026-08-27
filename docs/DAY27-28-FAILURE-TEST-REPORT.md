# ALANET — Day 27–28 Failure Test Report

Дата: 2026-08-27

## Что сделано

- Подготовлена матрица failure tests: [FAILURE-TEST-MATRIX.md](./FAILURE-TEST-MATRIX.md).
- Добавлен safe smoke runner: `infra/scripts/day27_28_failure_smoke.py`.
- Runner отделяет безопасные проверки от manual-gated destructive сценариев.
- Обновлены `ROADMAP-30-DAYS.md` и `ROADMAP-30-DAYS-SHORT.md`.

## Прогон safe smoke

Команда:

```bash
python infra/scripts/day27_28_failure_smoke.py
```

Результат:

```text
ALANET Day 27-28 smoke result: OK
```

Примечание: в локальной Windows-среде backend dependencies не установлены, поэтому backend unit tests корректно отмечены как `SKIP`. В CI/WSL/prod после `pip install -r backend/requirements.txt` они будут выполняться полноценно.

## Прогон read-only HTTP smoke

Команда:

```bash
python infra/scripts/day27_28_failure_smoke.py --live-readonly
```

Результат:

| Check | Expected | Result |
|---|---:|---:|
| `https://alanet.ru` | 200 | 200 |
| `https://account.alanet.ru` | 200 | 200 |
| `https://api.alanet.ru/health` | 200 | 200 |
| `https://panel.alanet.ru` | 200 | 200 |
| `https://sub.alanet.ru` | 404 | 404 |

Итог: `OK`.

## Что безопасно автоматизировано

- backend unit smoke;
- наличие failure-test документации;
- static check rate-limit matrix;
- read-only HTTP checks публичных сервисов.

## Что остается manual-gated

Эти проверки нельзя запускать без отдельного окна и подтвержденного rollback:

- остановка Remnawave;
- остановка production-ноды;
- реальный YooKassa платеж;
- revoke/disable реального клиента;
- rollback production image;
- firewall changes на shared VPS.

## Статус Day 27–28

| День | Цель | Статус | Комментарий |
|---|---|---|---|
| 27 | Payment/provisioning failure tests | Подготовлено | Нужен отдельный staging/prod-safe payment window |
| 28 | Infrastructure failure tests | Подготовлено | Destructive сценарии только manual-gated |

