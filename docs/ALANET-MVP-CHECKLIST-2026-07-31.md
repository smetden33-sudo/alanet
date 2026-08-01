# ALANET — общий чек-лист пройденной работы

Дата фиксации: 31.07.2026  
Статус: production MVP развивается как коммерческая платформа первых продаж.

## 1. Production-контур

- [x] Основной сервер production развернут.
- [x] Домены работают:
  - [x] `alanet.ru`;
  - [x] `account.alanet.ru`;
  - [x] `api.alanet.ru`;
  - [x] `panel.alanet.ru`;
  - [x] `monitor.alanet.ru`.
- [x] Caddy обслуживает сайт/API/панели.
- [x] SSL работает.
- [x] Backend API отвечает `/health`.
- [x] Web/frontend доступен.
- [x] Telegram bot подключен к backend.
- [x] YooKassa подключена.
- [x] Remnawave используется как control plane для Xray/nodes.
- [x] PostgreSQL работает в production.

## 2. Telegram bot и продажи

- [x] Бот подключен.
- [x] Администратор привязан к Telegram ID.
- [x] Клиент регистрируется через Telegram ID.
- [x] Убран обязательный email-шаг из логики Telegram-продажи.
- [x] Убрана кнопка/логика личного кабинета из Telegram bot, где она мешала клиентскому пути.
- [x] Добавлен пробный тариф на 24 часа.
- [x] Тарифы приведены к логике “безлимитный трафик / 1 устройство / все доступные локации / поддержка”.
- [x] Текст оффера и поддержки обновлён.
- [x] Проверена логика первой тестовой оплаты и provisioning.
- [x] Добавлена проверка `plan_id` в metadata YooKassa.
- [x] Добавлен механизм повторного provisioning.

## 3. Admin MVP в Telegram

- [x] `/admin` — список админ-команд.
- [x] `/stats` — статистика клиентов/заказов.
- [x] `/user` — карточка клиента.
- [x] `/grant` — ручная выдача тарифа.
- [x] `/extend` — ручное продление.
- [x] `/revoke` — отзыв доступа.
- [x] `/nodes` — состояние нод.
- [x] `/orders` — последние заказы.
- [x] `/health` — полная диагностика.
- [x] `/ports` — проверка host-портов Remnawave.
- [x] `/backup` — статус backup и restore-test.
- [x] `/retry_failed` — повтор failed provisioning.
- [x] `/node <name>` — карточка ноды.
- [x] `/payments` — последние оплаты.
- [x] `/finance` — финансовая сверка YooKassa.
- [x] `/audit [дни]` — журнал админских действий.
- [x] Роли администратора разделены по правам.
- [x] Ручные опасные действия требуют подтверждения.
- [x] Admin action audit пишется в БД.

## 4. YooKassa и финансовая надёжность

- [x] Подключен test shop.
- [x] Подключен production shop.
- [x] Webhook URL зафиксирован: `/webhooks/yookassa`.
- [x] Backend проверяет статус платежа через API.
- [x] После успешного платежа запускается provisioning.
- [x] Добавлена явная проверка plan metadata.
- [x] Добавлена daily finance reconciliation.
- [x] Ищутся аномалии:
  - [x] оплачено в YooKassa, но не ACTIVE у нас;
  - [x] ACTIVE у нас, но payment не succeeded;
  - [x] расхождение суммы/status.

## 5. Nodes, registry, ports, monitoring

- [x] Составлен и используется node registry.
- [x] Ноды синхронизируются с production-конфигурацией.
- [x] Добавлены host-port проверки из Remnawave hosts.
- [x] Проверка портов не требует ручного списка портов.
- [x] Добавлен Remnawave drift report.
- [x] Beszel установлен.
- [x] Ноды добавлены в мониторинг.
- [x] Health-check смотрит сайт, API, bot, Remnawave, hosts, load, disk.
- [x] Для `/api` и `/ports` применён incident threshold: авария только после повторных падений.
- [x] Повторные одинаковые alert’ы подавляются до восстановления.

## 6. Backup, внешний архив и restore-test

- [x] Локальный backup PostgreSQL и конфигураций.
- [x] Backup включает:
  - [x] billing PostgreSQL;
  - [x] Remnawave PostgreSQL;
  - [x] `.env`;
  - [x] Caddy;
  - [x] Remnawave config;
  - [x] node registry;
  - [x] Beszel compose.
- [x] Включено client-side encryption backup.
- [x] Настроен rclone.
- [x] Настроен внешний Timeweb S3 bucket.
- [x] Проверена выгрузка внешней encrypted копии.
- [x] Добавлен weekly restore-test.
- [x] Restore-test восстанавливает dump во временный PostgreSQL.
- [x] Restore-test проверяет таблицы и ключевые записи.
- [x] Статусы backup/restore пишутся в JSON.
- [x] `/backup`, `/health`, daily report читают статусы backup/restore.

## 7. IaC и автоматизация новых нод

- [x] Подготовлена идея мульти-нодовой архитектуры: один control plane, много geo-нod.
- [x] Описан подход Terraform + Ansible.
- [x] Оформляется модуль `vpn-node`.
- [x] Оформляется Ansible playbook для добавления ноды одной командой.
- [x] Перед реальным созданием нод предусмотрен прогон в WSL/Linux/CI.

## 8. Документация и roadmap

- [x] Зафиксирована production risk map.
- [x] Зафиксирована production-конфигурация.
- [x] Составлен план развития на 30 дней.
- [x] День 1 оформлен как аудит и карта рисков.
- [x] День 2–3 оформлен как авторизация/RBAC.
- [x] День 4 оформлен как external encrypted backup + restore-test.
- [x] День 5–7 оформлен как эксплуатационная надёжность и visibility.
- [x] Rollback-точки документируются.

## 9. Что осталось сделать следующим этапом

- [ ] Расширить или разгрузить диск prod.
- [ ] Добавить S3 lifecycle/retention на стороне Timeweb.
- [ ] Сделать staging-контур:
  - [ ] отдельная база;
  - [ ] test YooKassa shop;
  - [ ] test Telegram bot;
  - [ ] mock/test Remnawave;
  - [ ] test node profile.
- [ ] Довести Terraform/Ansible до команды “создать и зарегистрировать ноду”.
- [ ] Сделать полноценный Incident mode dashboard.
- [ ] Вынести secrets rotation в отдельный runbook.
- [ ] Добавить anti-fraud ограничения для trial.
- [ ] Добавить grace period перед отключением подписки.

