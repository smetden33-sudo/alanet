# ALANET — Failure Test Matrix

Дата: 2026-08-27

Статус: план тестирования отказов перед RC и production release.

Отчёт последнего безопасного прогона: [DAY27-28-FAILURE-TEST-REPORT.md](./DAY27-28-FAILURE-TEST-REPORT.md).

## Цель

Проверить, что ошибки не приводят к потере оплаты, двойной выдаче доступа или молчаливой деградации сервиса.

## Матрица тестов

| Сценарий | Что имитируем | Ожидаемый результат | Ready | Risk |
|---|---|---|---|---|
| Успешный платеж | YooKassa `payment.succeeded` | Подписка активируется ровно один раз | Нет | Двойная выдача |
| Неуспешный платеж | Отказ оплаты | Заказ остается неактивным, клиент видит ошибку | Нет | Непонятный UX |
| Повторный webhook | Один и тот же платеж дважды | Второй вызов не меняет состояние | Да | Дублирование |
| Remnawave недоступен | API/host outage | Заказ уходит в `PROVISIONING_FAILED` | Нет | Потеря доступа после оплаты |
| Одна нода недоступна | Ping/port fail | Сервис продолжает работать на остальных нодах | Нет | Ложная уверенность в покрытии |
| Истекшая подписка | Expire date reached | Доступ отключается по правилам | Да | Раннее или позднее отключение |
| Продление до/после истечения | Renew flow | Дата окончания считается корректно | Нет | Ошибка срока подписки |
| Повторный trial | Новый Telegram ID / device / email | Trial не выдается повторно | Да | Abuse |
| Ручная выдача | `/grant` | Аудит и одноразовое изменение | Да | Ошибочный доступ |
| Ручное продление | `/extend` | Аудит и корректная дата окончания | Да | Неверный тариф |
| Ручной отзыв | `/revoke` | Доступ отключается, аудит сохраняется | Да | Случайный отзыв |
| Restore rollback | Откат на backup | Система возвращается в рабочее состояние | Да | Неполный rollback |

## Порядок прогона

1. Начать с payment/webhook сценариев.
2. Потом проверить Remnawave и node failures.
3. Затем выполнить lifecycle и admin actions.
4. В конце прогнать restore/rollback rehearsal.

## Safe automation

Безопасный smoke runner:

```bash
python infra/scripts/day27_28_failure_smoke.py
```

Он не меняет production-состояние и проверяет:

- backend unit checks;
- наличие failure-test документации;
- rate-limit matrix для payment/auth/webhook endpoint.

Read-only HTTP проверка публичных сервисов:

```bash
python infra/scripts/day27_28_failure_smoke.py --live-readonly
```

Она делает только `GET`-проверки сайта, кабинета, API health, Remnawave panel и корня subscription domain.

## Manual-gated tests

Эти сценарии нельзя запускать автоматически без отдельного окна:

- имитация падения Remnawave;
- остановка production-ноды;
- реальный YooKassa payment;
- revoke/disable реального клиента;
- rollback production image;
- firewall changes на shared VPS.

Для них нужен отдельный change window, fresh backup и подтвержденный rollback.
