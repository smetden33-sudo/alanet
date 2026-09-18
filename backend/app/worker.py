import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from celery import Celery
from celery.schedules import crontab
from sqlalchemy import func, select
from .config import get_settings
from .db import SessionLocal, engine
from .financial_reconciliation import reconcile_yookassa_finance
from .integrations.remnawave import RemnawaveClient
from .integrations.yookassa import YooKassaClient
from .models import AuditLog, Customer, Order, OrderStatus, Payment, Subscription, SubscriptionStatus, WebhookEvent
from .notifications import notify_admin, send_telegram_message
from .remnawave_registry import compare_registry_to_remnawave, load_node_registry
from .services import retry_failed_provisioning

settings = get_settings()
log = logging.getLogger(__name__)
celery = Celery("billing", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json", timezone="UTC", beat_schedule={
    "retry-provisioning": {"task": "app.worker.retry_provisioning", "schedule": 60.0},
    "reconcile-payments": {"task": "app.worker.reconcile_payments", "schedule": 300.0},
    "subscription-lifecycle": {"task": "app.worker.subscription_lifecycle", "schedule": 300.0},
    "expired-telegram-access": {"task": "app.worker.expired_telegram_access", "schedule": 300.0},
    "node-audit": {"task": "app.worker.node_audit", "schedule": crontab(hour="*/6", minute=0)},
    "daily-admin-report": {"task": "app.worker.daily_admin_report", "schedule": crontab(hour=6, minute=0)},
    "daily-finance-reconciliation": {"task": "app.worker.daily_finance_reconciliation", "schedule": crontab(hour=6, minute=20)},
})

MONITOR_DIR = Path("/var/lib/alanet-monitor")


def run_async_task(coro):
    """Run one Celery coroutine without reusing asyncpg connections across event loops."""
    async def execute():
        try:
            return await coro
        finally:
            await engine.dispose()

    return asyncio.run(execute())


async def _tcp_port_open(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


def _resource_snapshot() -> str:
    try:
        with open("/proc/loadavg", encoding="utf-8") as file:
            load_1m = file.read().split()[0]
        with open("/proc/meminfo", encoding="utf-8") as file:
            meminfo = {}
            for line in file:
                key, value = line.split(":", 1)
                meminfo[key] = int(value.strip().split()[0])
        memory_percent = int((1 - meminfo["MemAvailable"] / meminfo["MemTotal"]) * 100)
    except Exception:
        load_1m = "n/a"
        memory_percent = -1
    memory_label = f"{memory_percent}%" if memory_percent >= 0 else "n/a"
    return f"memory {memory_label}, load {load_1m}"


def _status_age_hours(timestamp: str | None) -> float | None:
    if not timestamp:
        return None
    try:
        created_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return (datetime.now(UTC) - created_at.astimezone(UTC)).total_seconds() / 3600
    except ValueError:
        return None


def _read_monitor_status(name: str) -> dict | None:
    try:
        return json.loads((MONITOR_DIR / name).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        log.exception("monitor status read failed: %s", name)
        return {"status": "failed", "message": "status json unreadable"}


def _backup_restore_snapshot() -> list[str]:
    lines: list[str] = []
    backup = _read_monitor_status("backup.status.json")
    if backup:
        age = _status_age_hours(backup.get("timestamp"))
        age_text = f"{age:.1f}h" if age is not None else "unknown"
        archive = Path(str(backup.get("archive") or "")).name or "unknown"
        external = backup.get("external_archive") or "none"
        external_state = "внешняя=да" if external != "none" else "внешняя=нет"
        lines.append(f"Резервная копия: {backup.get('status')} {archive}, возраст {age_text}, {external_state}")
    else:
        lines.append("Резервная копия: файл состояния отсутствует")
    restore = _read_monitor_status("restore-test.status.json")
    if restore:
        age = _status_age_hours(restore.get("timestamp"))
        age_text = f"{age:.1f}h" if age is not None else "unknown"
        lines.append(
            "Тест восстановления: "
            f"{restore.get('status')} источник={restore.get('source')}, возраст {age_text}, "
            f"таблицы={restore.get('tables')}, клиенты={restore.get('customers')}, "
            f"заказы={restore.get('orders')}, подписки={restore.get('subscriptions')}, платежи={restore.get('payments')}"
        )
    else:
        lines.append("Тест восстановления: файл состояния отсутствует")
    return lines


async def _retry_provisioning() -> int:
    completed = 0
    async with SessionLocal() as session:
        order_ids = list((await session.scalars(select(Order.id).where(Order.status == OrderStatus.PROVISIONING_FAILED).limit(25))).all())
        for order_id in order_ids:
            try:
                await retry_failed_provisioning(session, settings, order_id)
                completed += 1
            except Exception:
                await session.rollback()
                log.exception("provisioning retry failed for order %s", order_id)
    return completed


async def _reconcile_payments() -> int:
    updated = 0
    cutoff = datetime.now(UTC) - timedelta(minutes=5)
    async with SessionLocal() as session:
        rows = (await session.execute(select(Payment, Order).join(Order, Payment.order_id == Order.id).where(Order.status == OrderStatus.PAYMENT_PENDING, Order.created_at < cutoff).limit(100))).all()
        client = YooKassaClient(settings)
        for payment, order in rows:
            if not payment.yookassa_payment_id:
                continue
            remote = await client.get_payment(payment.yookassa_payment_id)
            payment.status = remote["status"]
            if remote["status"] == "canceled":
                order.status = OrderStatus.CANCELED
                updated += 1
        await session.commit()
    return updated


async def _subscription_lifecycle() -> dict[str, int]:
    now = datetime.now(UTC)
    expired_count = 0
    notice_count = 0
    async with SessionLocal() as session:
        expired = list((await session.scalars(select(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE, Subscription.expires_at <= now).limit(100))).all())
        for subscription in expired:
            subscription_id = str(subscription.id)
            try:
                await RemnawaveClient(settings).update_user(
                    subscription.remnawave_user_id,
                    user_uuid=str(subscription.remnawave_legacy_uuid) if subscription.remnawave_legacy_uuid else None,
                    status="DISABLED",
                )
                subscription.status = SubscriptionStatus.EXPIRED
                session.add(AuditLog(actor="worker:lifecycle", action="subscription_expired", entity="subscription", entity_id=str(subscription.id), details={"expires_at": subscription.expires_at.isoformat()}))
                customer = await session.get(Customer, subscription.customer_id)
                await session.commit()
                expired_count += 1
                if customer and customer.telegram_id:
                    await send_telegram_message(settings, customer.telegram_id, "Срок подписки ALANET закончился. Откройте раздел «Купить подписку», чтобы восстановить доступ.")
                if customer:
                    customer_label = customer.telegram_username or (f"TG {customer.telegram_id}" if customer.telegram_id else customer.email)
                    await notify_admin(
                        settings,
                        "ALANET: subscription expired.\n"
                        f"Client: {customer_label}\n"
                        f"Subscription ID: {subscription.id}\n"
                        f"Expired at: {subscription.expires_at.astimezone().strftime('%d.%m.%Y %H:%M')}",
                    )
            except Exception:
                await session.rollback()
                log.exception("subscription_expiry_failed subscription_id=%s", subscription_id)

        deadline = now + timedelta(hours=72)
        upcoming = list((await session.scalars(select(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE, Subscription.expires_at > now, Subscription.expires_at <= deadline).limit(200))).all())
        for subscription in upcoming:
            hours = (subscription.expires_at - now).total_seconds() / 3600
            action = "expiry_notice_24h" if hours <= 24 else "expiry_notice_72h"
            already_sent = await session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == action, AuditLog.entity == "subscription", AuditLog.entity_id == str(subscription.id)))
            if already_sent:
                continue
            customer = await session.get(Customer, subscription.customer_id)
            if not customer or not customer.telegram_id:
                continue
            label = "меньше суток" if hours <= 24 else "меньше трёх дней"
            sent = await send_telegram_message(settings, customer.telegram_id, f"До окончания подписки ALANET осталось {label}. Продлить её можно через раздел «Купить подписку» — новый срок добавится к текущей дате.")
            if sent:
                session.add(AuditLog(actor="worker:lifecycle", action=action, entity="subscription", entity_id=str(subscription.id), details={"expires_at": subscription.expires_at.isoformat()}))
                await session.commit()
                notice_count += 1
    return {"expired": expired_count, "notices": notice_count}


async def _expired_telegram_access() -> int:
    """Restore a short Telegram-only fallback for expired Remnawave users."""
    squad_id = settings.remnawave_expired_squad_id.strip()
    if not squad_id:
        log.warning("expired Telegram access is disabled: REMNAWAVE_EXPIRED_SQUAD_ID is empty")
        return 0
    if settings.remnawave_expired_grace_days <= 0:
        log.error("expired Telegram access is disabled: REMNAWAVE_EXPIRED_GRACE_DAYS must be positive")
        return 0

    users = await RemnawaveClient(settings).list_users()
    expired_users = [user for user in users if user.get("status") == "EXPIRED" and user.get("uuid")]
    if not expired_users:
        return 0

    expiry = datetime.now(UTC) + timedelta(days=settings.remnawave_expired_grace_days)
    updated = 0
    client = RemnawaveClient(settings)
    async with SessionLocal() as session:
        for user in expired_users:
            try:
                await client.update_user(
                    int(user["id"]),
                    user_uuid=str(user["uuid"]),
                    status="ACTIVE",
                    expireAt=expiry.isoformat(),
                    hwidDeviceLimit=1,
                    activeInternalSquads=[squad_id],
                )
                session.add(AuditLog(
                    actor="worker:expired-telegram-access",
                    action="expired_telegram_access_granted",
                    entity="remnawave_user",
                    entity_id=str(user["uuid"]),
                    details={"user_id": user.get("id"), "squad_id": squad_id, "expires_at": expiry.isoformat()},
                ))
                await session.commit()
                updated += 1
            except Exception:
                await session.rollback()
                log.exception("expired Telegram access grant failed for user %s", user.get("uuid"))
    if updated:
        await notify_admin(settings, f"ALANET: Telegram-only fallback granted to {updated} expired Remnawave users for {settings.remnawave_expired_grace_days} days.")
    return updated


def _translate_node_audit_message(message: str) -> str:
    """Translate registry drift details for the administrator-facing report."""
    translations = (
        ("node is disconnected in Remnawave.", "нода отключена в Remnawave."),
        ("Remnawave has node not present as active in registry:", "В Remnawave есть нода, отсутствующая среди активных в реестре:"),
        ("Remnawave has enabled host not present as active in registry:", "В Remnawave есть включённый host, отсутствующий среди активных в реестре:"),
        ("Registry node ", "Нода реестра "),
        (" is missing in Remnawave.", " отсутствует в Remnawave."),
        ("host ", "host "),
        (" is disabled in Remnawave.", " отключён в Remnawave."),
        ("registry host IP ", "IP host в реестре "),
        (", Remnawave IP ", ", IP в Remnawave "),
        ("registry port ", "порт в реестре "),
        (", Remnawave port ", ", порт в Remnawave "),
        ("registry UUID ", "UUID в реестре "),
        (", Remnawave UUID ", ", UUID в Remnawave "),
        ("is not bound to registry node UUID ", "не привязан к UUID ноды из реестра "),
        ("Remnawave node is not connected.", "нода Remnawave не подключена."),
    )
    translated = message
    for source, target in translations:
        translated = translated.replace(source, target)
    return translated


async def _node_audit() -> bool:
    """Send a six-hourly read-only audit of all Remnawave nodes and hosts."""
    now = datetime.now(UTC)
    try:
        client = RemnawaveClient(settings)
        nodes, hosts = await asyncio.gather(client.list_nodes(), client.list_hosts())
        registry = load_node_registry()
        drift = compare_registry_to_remnawave(registry, nodes, hosts)
        critical_drift = [item for item in drift if item.severity == "critical"]
        warning_drift = [item for item in drift if item.severity == "warning"]

        enabled_hosts = [host for host in hosts if not host.get("isDisabled", False)]
        port_checks = [
            (host, _tcp_port_open(str(host.get("address")), int(host.get("port"))))
            for host in enabled_hosts
            if host.get("address") and host.get("port")
        ]
        port_results = await asyncio.gather(*(check for _host, check in port_checks)) if port_checks else []
        failed_ports = [
            f"{host.get('remark') or host.get('name') or host.get('address')} {host.get('address')}:{host.get('port')}"
            for (host, _check), ok in zip(port_checks, port_results, strict=False)
            if not ok
        ]
        down_nodes = [str(node.get("name") or node.get("uuid") or "unknown") for node in nodes if node.get("isConnected") is False]
        connected = sum(1 for node in nodes if node.get("isConnected") is True)

        lines = [
            "ALANET: аудит нод",
            f"Время: {now.astimezone().strftime('%d.%m.%Y %H:%M %Z')}",
            f"Ноды: подключены {connected} из {len(nodes)}",
            f"Активных host: {len(enabled_hosts)}",
            f"Расхождения: критических {len(critical_drift)}, предупреждений {len(warning_drift)}",
            f"Недоступных host-портов: {len(failed_ports)}",
        ]
        if down_nodes:
            lines.append("⛔ Отключённые ноды: " + ", ".join(down_nodes[:20]))
        if failed_ports:
            lines.append("⛔ Недоступные порты: " + "; ".join(failed_ports[:20]))
        for item in (critical_drift + warning_drift)[:20]:
            icon = "⛔" if item.severity == "critical" else "⚠️"
            lines.append(f"{icon} {_translate_node_audit_message(item.message)}")
        if not down_nodes and not failed_ports and not drift:
            lines.append("✅ Все ноды, host-порты и реестр работают без проблем.")
        elif len(critical_drift) + len(warning_drift) > 20:
            lines.append(f"… ещё записей о расхождениях: {len(drift) - 20}")
    except Exception as exc:
        log.exception("node_audit_failed")
        lines = [
            "ALANET: аудит нод",
            f"Время: {now.astimezone().strftime('%d.%m.%Y %H:%M %Z')}",
            f"⛔ Не удалось выполнить аудит: {type(exc).__name__}",
        ]
    return await notify_admin(settings, "\n".join(lines))


async def _daily_admin_report() -> bool:
    now = datetime.now(UTC)
    since = now - timedelta(days=1)
    async with SessionLocal() as session:
        customers = await session.scalar(select(func.count()).select_from(Customer).where(Customer.created_at >= since))
        payments = await session.scalar(select(func.count()).select_from(Payment).where(Payment.status == "succeeded", Payment.paid_at >= since))
        revenue = await session.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "succeeded", Payment.paid_at >= since))
        active = await session.scalar(select(func.count()).select_from(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE))
        failed = await session.scalar(select(func.count()).select_from(Order).where(Order.status == OrderStatus.PROVISIONING_FAILED))
        expiring_24h = await session.scalar(select(func.count()).select_from(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE, Subscription.expires_at > now, Subscription.expires_at <= now + timedelta(hours=24)))
        expiring_72h = await session.scalar(select(func.count()).select_from(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE, Subscription.expires_at > now, Subscription.expires_at <= now + timedelta(hours=72)))
        webhook_errors = await session.scalar(select(func.count()).select_from(WebhookEvent).where(WebhookEvent.processing_status != "PROCESSED", WebhookEvent.processed_at >= since))
    try:
        client = RemnawaveClient(settings)
        nodes = await client.list_nodes()
        connected = sum(1 for node in nodes if node.get("isConnected"))
        node_status = f"{connected}/{len(nodes)}"
        down_nodes = [node.get("name", "unknown") for node in nodes if not node.get("isConnected")]
        all_hosts = await client.list_hosts()
        hosts = [host for host in all_hosts if not host.get("isDisabled", False)]
        registry = load_node_registry()
        drift = compare_registry_to_remnawave(registry, nodes, all_hosts)
        drift_critical = sum(1 for item in drift if item.severity == "critical")
        drift_warnings = sum(1 for item in drift if item.severity == "warning")
        port_checks = [
            (host, _tcp_port_open(str(host.get("address")), int(host.get("port"))))
            for host in hosts
            if host.get("address") and host.get("port")
        ]
        port_results = await asyncio.gather(*(check for _host, check in port_checks)) if port_checks else []
        failed_ports = [
            f"{host.get('remark') or host.get('name') or host.get('address')} {host.get('address')}:{host.get('port')}"
            for (host, _check), ok in zip(port_checks, port_results, strict=False)
            if not ok
        ]
    except Exception:
        node_status = "check failed"
        down_nodes = ["Remnawave API unavailable"]
        failed_ports = ["host check failed"]
        drift_critical = -1
        drift_warnings = -1
    revenue = revenue or 0
    lines = [
        "Ежедневный отчёт ALANET",
        f"Период: {since.astimezone().strftime('%d.%m %H:%M')} — {now.astimezone().strftime('%d.%m %H:%M')}",
        "",
        f"Новые клиенты: {customers}",
        f"Успешные платежи: {payments}",
        f"Доход за 24 часа: {revenue:.2f} RUB",
        f"Активные подписки: {active}",
        f"Ошибки выдачи: {failed}",
        f"Истекают в течение 24 часов: {expiring_24h}",
        f"Истекают в течение 72 часов: {expiring_72h}",
        f"Ошибки вебхуков: {webhook_errors}",
        f"Ноды: {node_status}",
        f"Расхождения реестра: критических {drift_critical}, предупреждений {drift_warnings}",
        f"Ресурсы: {_resource_snapshot()}",
    ]
    lines.extend(_backup_restore_snapshot())
    if down_nodes:
        lines.append("Недоступные ноды: " + ", ".join(down_nodes[:10]))
    if failed_ports:
        lines.append("Недоступные host-порты: " + "; ".join(failed_ports[:10]))
    if not down_nodes and not failed_ports and failed == 0 and webhook_errors == 0:
        lines.append("Итог: проблем не обнаружено.")
    return await notify_admin(settings, "\n".join(lines))


async def _daily_finance_reconciliation() -> bool:
    async with SessionLocal() as session:
        lines, issues = await reconcile_yookassa_finance(session, settings, days=30, limit=200)
    if not issues:
        lines = lines[:9] + ["Status: ok — no commercial anomalies."]
    return await notify_admin(settings, "\n".join(lines))

@celery.task(name="app.worker.retry_provisioning")
def retry_provisioning() -> int:
    return run_async_task(_retry_provisioning())


@celery.task(name="app.worker.reconcile_payments")
def reconcile_payments() -> int:
    return run_async_task(_reconcile_payments())


@celery.task(name="app.worker.subscription_lifecycle")
def subscription_lifecycle() -> dict[str, int]:
    return run_async_task(_subscription_lifecycle())


@celery.task(name="app.worker.expired_telegram_access")
def expired_telegram_access() -> int:
    return run_async_task(_expired_telegram_access())


@celery.task(name="app.worker.node_audit")
def node_audit() -> bool:
    return run_async_task(_node_audit())


@celery.task(name="app.worker.daily_admin_report")
def daily_admin_report() -> bool:
    return run_async_task(_daily_admin_report())


@celery.task(name="app.worker.daily_finance_reconciliation")
def daily_finance_reconciliation() -> bool:
    return run_async_task(_daily_finance_reconciliation())
