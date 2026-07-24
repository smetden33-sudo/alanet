import asyncio
from datetime import UTC, datetime, timedelta
from celery import Celery
from sqlalchemy import select
from .config import get_settings
from .db import SessionLocal
from .integrations.yookassa import YooKassaClient
from .models import Order, OrderStatus, Payment
from .services import provision_order

settings = get_settings()
celery = Celery("billing", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json", timezone="UTC", beat_schedule={
    "retry-provisioning": {"task": "app.worker.retry_provisioning", "schedule": 60.0},
    "reconcile-payments": {"task": "app.worker.reconcile_payments", "schedule": 300.0},
})


async def _retry_provisioning() -> int:
    completed = 0
    async with SessionLocal() as session:
        order_ids = list((await session.scalars(select(Order.id).where(Order.status == OrderStatus.PROVISIONING_FAILED).limit(25))).all())
        for order_id in order_ids:
            try:
                await provision_order(session, settings, order_id)
                completed += 1
            except Exception:
                await session.rollback()
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


@celery.task(name="app.worker.retry_provisioning")
def retry_provisioning() -> int:
    return asyncio.run(_retry_provisioning())


@celery.task(name="app.worker.reconcile_payments")
def reconcile_payments() -> int:
    return asyncio.run(_reconcile_payments())
