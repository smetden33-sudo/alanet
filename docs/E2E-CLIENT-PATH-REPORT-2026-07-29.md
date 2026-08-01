# E2E client path check — 2026-07-29

Goal: verify the first-client path from Telegram `/start` to connection and identify places where the client can get stuck or where manual admin work is still required.

## Checked

- Public domains respond with HTTP 200:
  - `https://alanet.ru`
  - `https://account.alanet.ru`
  - `https://api.alanet.ru/health`
  - `https://monitor.alanet.ru`
  - `https://panel.alanet.ru`
- Frontend quality gates:
  - `npm.cmd run lint` passed.
  - `npm.cmd run build` passed.
- Backend syntax:
  - `python -m compileall backend/app` passed.
- Source encoding:
  - tracked source files are valid UTF-8.
  - no real `???` or replacement-character mojibake was found in source files.

## Telegram purchase path

Expected first-client flow:

1. Client opens `https://t.me/alanet_bot`.
2. Client presses `/start`.
3. Client selects a plan.
4. For the trial plan, the bot provisions access immediately.
5. For paid plans, the bot creates a YooKassa checkout using the immutable numeric Telegram ID as the customer identity.
6. The client pays on YooKassa.
7. YooKassa sends `payment.succeeded` to `https://api.alanet.ru/webhooks/yookassa`.
8. Backend verifies the payment via YooKassa API and checks `order_id`, `customer_id`, `plan_id`, amount and currency.
9. Backend provisions or extends the Remnawave subscription.
10. Client receives/opens the subscription URL and follows `/setup` instructions.

Important: the Telegram path does not ask the client to enter email. A technical email is generated from Telegram ID for YooKassa receipt requirements.

## Issues found and fixed

### Website routed paid tariffs to disabled checkout

The public website paid plan buttons led to `/checkout`, while public website checkout is intentionally paused. This could confuse a first client who starts from the site instead of Telegram.

Fixed in `app/page.tsx`:

- paid tariff buttons now open `https://t.me/alanet_bot`;
- top button changed from "Личный кабинет" to "Открыть бота";
- footer link changed from `/checkout` to `Telegram-бот`.

## Known limitations of this check

- A real Telegram client session cannot be fully automated through Bot API: bots cannot initiate a user-side `/start` conversation with themselves.
- Local Docker is unavailable on this workstation, so container-level integration testing was not possible here.
- Backend dependency installation into a local Python 3.14 virtual environment did not complete in time; likely some packages need wheels unavailable for Python 3.14. Backend syntax was checked, but unit tests should be run in the same Python/Docker environment as production.

## Remaining manual E2E test

Use a real Telegram account that is not the admin account:

1. Open `https://t.me/alanet_bot`.
2. Send `/start`.
3. Select `Пробный`.
4. Confirm that the bot returns a subscription URL.
5. Open the URL in the recommended client app.
6. Confirm that only the intended trial location is available.
7. Select paid plan `Старт`.
8. Complete a YooKassa test or low-value live payment when allowed.
9. Confirm that the same Telegram ID keeps the same customer record and extends the existing subscription instead of creating a duplicate.
10. Confirm that the admin bot receives payment/provisioning notifications.

## Readiness verdict

The Telegram-first sales path is architecturally ready for first controlled sales, but before public traffic it still needs one real user-side Telegram payment run with a non-admin account.
