import asyncio
import logging
from datetime import UTC, datetime, timedelta
from celery import Celery
from celery.schedules import crontab
from sqlalchemy import func, select
from .config import get_settings
from .db import SessionLocal
from .integrations.remnawave import RemnawaveClient
from .integrations.yookassa import YooKassaClient
from .models import AuditLog, Customer, Order, OrderStatus, Payment, Subscription, SubscriptionStatus
from .notifications import notify_admin, send_telegram_message
from .services import retry_failed_provisioning

settings = get_settings()
log = logging.getLogger(__name__)
celery = Celery("billing", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json", timezone="UTC", beat_schedule={
    "retry-provisioning": {"task": "app.worker.retry_provisioning", "schedule": 60.0},
    "reconcile-payments": {"task": "app.worker.reconcile_payments", "schedule": 300.0},
    "subscription-lifecycle": {"task": "app.worker.subscription_lifecycle", "schedule": 300.0},
    "daily-admin-report": {"task": "app.worker.daily_admin_report", "schedule": crontab(hour=6, minute=0)},
})


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
                    await send_telegram_message(settings, customer.telegram_id, "Срок подписки ALANET закончился. Откройте /account или раздел «Купить подписку», чтобы восстановить доступ.")
            except Exception:
                await session.rollback()
                log.exception("subscription_expiry_failed", subscription_id=subscription_id)

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
            sent = await send_telegram_message(settings, customer.telegram_id, f"До окончания подписки ALANET осталось {label}. Продлить её можно через /account — новый срок добавится к текущей дате.")
            if sent:
                session.add(AuditLog(actor="worker:lifecycle", action=action, entity="subscription", entity_id=str(subscription.id), details={"expires_at": subscription.expires_at.isoformat()}))
                await session.commit()
                notice_count += 1
    return {"expired": expired_count, "notices": notice_count}


async def _daily_admin_report() -> bool:
    now = datetime.now(UTC)
    since = now - timedelta(days=1)
    async with SessionLocal() as session:
        customers = await session.scalar(select(func.count()).select_from(Customer).where(Customer.created_at >= since))
        payments = await session.scalar(select(func.count()).select_from(Payment).where(Payment.status == "succeeded", Payment.paid_at >= since))
        active = await session.scalar(select(func.count()).select_from(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE))
        failed = await session.scalar(select(func.count()).select_from(Order).where(Order.status == OrderStatus.PROVISIONING_FAILED))
    try:
        nodes = await RemnawaveClient(settings).list_nodes()
        connected = sum(1 for node in nodes if node.get("isConnected"))
        node_status = f"{connected}/{len(nodes)}"
    except Exception:
        node_status = "ошибка проверки"
    return await notify_admin(settings, f"Ежедневный отчёт ALANET\nНовые клиенты: {customers}\nУспешные платежи: {payments}\nАктивные подписки: {active}\nОшибки provisioning: {failed}\nНоды: {node_status}")


@celery.task(name="app.worker.retry_provisioning")
def retry_provisioning() -> int:
    return asyncio.run(_retry_provisioning())


@celery.task(name="app.worker.reconcile_payments")
def reconcile_payments() -> int:
    return asyncio.run(_reconcile_payments())


@celery.task(name="app.worker.subscription_lifecycle")
def subscription_lifecycle() -> dict[str, int]:
    return asyncio.run(_subscription_lifecycle())


@celery.task(name="app.worker.daily_admin_report")
def daily_admin_report() -> bool:
    return asyncio.run(_daily_admin_report())
