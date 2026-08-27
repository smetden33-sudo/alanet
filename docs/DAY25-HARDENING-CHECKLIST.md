# ALANET — Day 25 Network/System Hardening Checklist

Дата: 2026-08-27

Цель: подтвердить, что production открыт наружу только там, где это нужно, а чувствительные сервисы остаются внутри приватного контура.

## Текущий вывод

Day 25 технически в основном закрыт:

- public edge проходит через Caddy;
- web и API проброшены на `127.0.0.1`;
- billing PostgreSQL и Redis не имеют публичного `ports`;
- Remnawave, subscription и Beszel должны открываться наружу только через reverse proxy;
- чувствительные публичные endpoint имеют rate limit;
- Docker services имеют memory limits;
- shared VPS ноды помечены как `do not reset firewall blindly`.

## Проверка публичной поверхности

| Проверка | Ожидаемый результат | Ready | Risk |
|---|---|---|---|
| `80/tcp` | открыт для HTTP/ACME redirect | Да | нужен для сертификатов |
| `443/tcp` | открыт для HTTPS | Да | основной публичный вход |
| `443/udp` | открыт для HTTP/3, если включён Caddy | Да | может быть закрыт без критичного влияния |
| `22/tcp` или нестандартный SSH | доступен только для администрирования | Частично | желательно ограничить admin CIDR |
| `8000/tcp` API | доступен только `127.0.0.1` | Да | публичный доступ запрещён |
| `3100/tcp` web | доступен только `127.0.0.1` | Да | публичный доступ запрещён |
| PostgreSQL billing | нет public port | Да | public exposure критичен |
| Redis billing | нет public port | Да | public exposure критичен |
| Beszel | доступен через `monitor.alanet.ru` | Да | нужен сильный пароль/2FA, если доступно |

## Rate-limit matrix

| Endpoint | Назначение | Текущий лимит | Ready | Risk |
|---|---|---:|---|---|
| `/api/v1/checkout` | создание платежа | 10/min per IP | Да | payment spam |
| `/api/v1/me/checkout` | продление из кабинета | 10/min per IP | Да | account abuse |
| `/api/v1/auth/telegram/exchange` | обмен Telegram login token | 10/min per IP | Да | brute force token |
| `/webhooks/yookassa` | YooKassa webhook | 120/min per IP | Да | replay/noise |
| `/webhooks/telegram` | Telegram webhook | 300/min per IP | Да | bot flood |

## Hardening checklist

- [ ] Перед изменениями проверить `/incident`.
- [ ] Проверить `ss -tulpn` на prod.
- [ ] Убедиться, что DB/Redis не слушают `0.0.0.0`.
- [ ] Проверить, что Caddy отдаёт security headers.
- [ ] Проверить, что `/api/docs` выключен на production.
- [ ] Проверить, что Remnawave panel не открывает лишние path.
- [ ] Проверить firewall rules.
- [ ] Проверить Docker log rotation.
- [ ] Проверить, что staging ports bind только на `127.0.0.1`.
- [ ] Проверить, что shared VPS firewall не сбрасывается автоматически.

## Что нельзя делать без отдельного окна

- Сбрасывать firewall на shared VPS.
- Закрывать SSH без второго подтвержденного доступа.
- Делать `docker system prune --volumes`.
- Переключать Caddy/Remnawave routes без smoke-test.
- Менять одновременно firewall и секреты.

## Acceptance

- [ ] `/incident` не показывает сетевую аварию.
- [ ] `/ports` показывает активные host-порты.
- [ ] `/health` видит API, Remnawave, backup и monitoring.
- [ ] Сайт, кабинет, API, панель и monitor доступны через HTTPS.
- [ ] DB/Redis не доступны из публичной сети.

