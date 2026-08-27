# ALANET — Security + Legal Readiness

Дата: 2026-08-27

Статус: базовые технические меры уже частично есть; этот документ фиксирует остаток работ перед публичным коммерческим запуском.

## Что уже закрыто

- firewall и публичные порты описаны в инфраструктуре;
- PostgreSQL и Redis не должны быть доступны извне;
- Telegram admin-доступ ограничен;
- rate limit и audit для чувствительных действий уже предусмотрены;
- локальные и внешние backup-ретеншены описаны;
- customer data deletion и retention уже описаны в operations runbook.

## Уже подготовленные рабочие артефакты

- [SECRET-INVENTORY.md](./SECRET-INVENTORY.md)
- [SECRET-ROTATION-RUNBOOK.md](./SECRET-ROTATION-RUNBOOK.md)
- [DAY24-ROTATION-CHECKLIST.md](./DAY24-ROTATION-CHECKLIST.md)
- [DAY25-HARDENING-CHECKLIST.md](./DAY25-HARDENING-CHECKLIST.md)
- [DAY26-LEGAL-READINESS-CHECKLIST.md](./DAY26-LEGAL-READINESS-CHECKLIST.md)

## Security readiness checklist

| Пункт | Артефакт | Ready | Risk |
|---|---|---|---|
| Secret inventory | Таблица ключей и дат последней ротации | Нет | Неясно, какой секрет старше и что менять первым |
| Telegram bot token rotation | Процедура замены без простоя | Нет | Потеря админ-оповещений и клиентского бота |
| YooKassa secret rotation | Пошаговый rollback checklist | Нет | Ошибки в оплатах и webhook |
| Remnawave token rotation | Новые токены + staged reconnect | Нет | Отвал provisioning или registry sync |
| DB/Redis password rotation | Обновление env + restart plan | Нет | Потеря соединения сервисов |
| Deploy SSH key rotation | Второй подтвержденный ключ до удаления старого | Нет | Риск потерять доступ к prod |
| Secret leakage audit | Проверка Git, docs, logs, backups | Частично | Секреты могут остаться в черновиках и архиве |

## Legal readiness checklist

| Пункт | Артефакт | Ready | Risk |
|---|---|---|---|
| Seller details | Реквизиты реального продавца | Нет | Нельзя безопасно включать публичный checkout |
| Public offer | Оферта для сайта и checkout | Нет | Юридически не оформлена продажа |
| Privacy policy | Политика конфиденциальности | Нет | Нет прозрачного режима обработки данных |
| Consent text | Согласие на обработку данных | Нет | Нет корректного пользовательского согласия |
| Refund rules | Правила возврата и отмены | Нет | Непрозрачные ожидания по платежам |
| Data retention | Сроки хранения данных и логов | Частично | Несогласованное хранение персональных данных |

## Что делать дальше

1. Согласовать порядок ротации секретов.
2. Получить и зафиксировать юридические реквизиты.
3. После этого включать публичный checkout и считать Day 24–26 закрытыми.
