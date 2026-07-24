import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .config import Settings
from .integrations.remnawave import RemnawaveClient
from .integrations.yookassa import YooKassaClient
from .models import Customer, Order, OrderStatus, Payment, Plan, Subscription, SubscriptionStatus, WebhookEvent


def extended_expiry(current: datetime | None, duration_days: int, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    base = current if current and current > now else now
    return base + timedelta(days=duration_days)


async def create_checkout(session: AsyncSession, settings: Settings, *, plan_slug: str, email: str, telegram_username: str | None) -> tuple[Order, str]:
    plan = await session.scalar(select(Plan).where(Plan.slug == plan_slug, Plan.is_active.is_(True)))
    if not plan:
        raise ValueError("unknown plan")
    customer = Customer(email=email, telegram_username=telegram_username)
    order = Order(customer=customer, plan=plan, amount=plan.price_rub, status=OrderStatus.CREATED)
    key = str(uuid.uuid4())
    session.add_all([customer, order])
    await session.flush()
    payment = Payment(order_id=order.id, idempotency_key=key, amount=plan.price_rub, status="CREATING")
    session.add(payment)
    result = await YooKassaClient(settings).create_payment(order_id=str(order.id), customer_id=str(customer.id), plan_id=str(plan.id), amount=plan.price_rub, email=email, return_url=f"{settings.public_site_url}/checkout/success?order={order.id}", idempotency_key=key)
    payment.yookassa_payment_id = result["id"]
    payment.status = result["status"]
    payment.raw_payload = result
    order.status = OrderStatus.PAYMENT_PENDING
    await session.commit()
    return order, result["confirmation"]["confirmation_url"]


async def accept_yookassa_webhook(session: AsyncSession, settings: Settings, payload: dict) -> str:
    if payload.get("event") != "payment.succeeded":
        return "ignored"
    payment_id = str(payload.get("object", {}).get("id", ""))
    if not payment_id:
        raise ValueError("payment id missing")
    existing = await session.scalar(select(WebhookEvent).where(WebhookEvent.provider == "yookassa", WebhookEvent.external_event_id == payment_id))
    if existing and existing.processing_status == "PROCESSED":
        return "duplicate"
    verified = await YooKassaClient(settings).get_payment(payment_id)
    payment = await session.scalar(select(Payment).where(Payment.yookassa_payment_id == payment_id))
    if not payment:
        raise ValueError("payment not found")
    order = await session.scalar(select(Order).where(Order.id == payment.order_id).with_for_update())
    if not order:
        raise ValueError("order not found")
    if not existing:
        existing = await session.scalar(select(WebhookEvent).where(WebhookEvent.provider == "yookassa", WebhookEvent.external_event_id == payment_id).with_for_update())
    amount = Decimal(verified["amount"]["value"])
    metadata = verified.get("metadata", {})
    valid = verified.get("status") == "succeeded" and verified["amount"]["currency"] == "RUB" and amount == order.amount and metadata.get("order_id") == str(order.id)
    if not valid:
        raise ValueError("payment verification failed")
    event = existing or WebhookEvent(provider="yookassa", external_event_id=payment_id, payload=payload)
    session.add(event)
    if order.status == OrderStatus.ACTIVE:
        event.processing_status = "PROCESSED"
        event.processed_at = datetime.now(UTC)
        await session.commit()
        return "duplicate"
    order.status = OrderStatus.PROVISIONING
    payment.status = "succeeded"
    payment.paid_at = datetime.fromisoformat(verified["captured_at"].replace("Z", "+00:00")) if verified.get("captured_at") else datetime.now(UTC)
    await session.commit()
    try:
        await provision_order(session, settings, order.id)
    except Exception:
        order = await session.get(Order, order.id)
        if order:
            order.status = OrderStatus.PROVISIONING_FAILED
        event = await session.scalar(select(WebhookEvent).where(WebhookEvent.provider == "yookassa", WebhookEvent.external_event_id == payment_id))
        if event:
            event.processing_status = "RETRY"
        await session.commit()
        raise
    event = await session.scalar(select(WebhookEvent).where(WebhookEvent.provider == "yookassa", WebhookEvent.external_event_id == payment_id))
    if event:
        event.processing_status = "PROCESSED"
        event.processed_at = datetime.now(UTC)
    await session.commit()
    return "processed"


async def provision_order(session: AsyncSession, settings: Settings, order_id: uuid.UUID) -> Subscription:
    order = await session.scalar(select(Order).where(Order.id == order_id))
    if not order:
        raise ValueError("order not found")
    customer, plan = await session.get(Customer, order.customer_id), await session.get(Plan, order.plan_id)
    subscription = await session.scalar(select(Subscription).where(Subscription.customer_id == order.customer_id))
    expiry = extended_expiry(subscription.expires_at if subscription else None, plan.duration_days)
    client = RemnawaveClient(settings)
    if subscription:
        await client.extend_subscription(subscription.remnawave_user_id, expiry)
        subscription.expires_at = expiry
        subscription.status = SubscriptionStatus.ACTIVE
    else:
        username = f"customer_{str(customer.id).replace('-', '')[:18]}"
        try:
            remote = await client.create_user(username=username, expire_at=expiry, traffic_limit_bytes=plan.traffic_limit_bytes, device_limit=plan.device_limit, squad_id=plan.remnawave_squad_id)
        except Exception:
            remote = await client.get_user_by_username(username)
        user_id, url, legacy_uuid = client.user_fields(remote)
        subscription = Subscription(customer_id=customer.id, remnawave_user_id=user_id, remnawave_legacy_uuid=legacy_uuid, subscription_url=url, starts_at=datetime.now(UTC), expires_at=expiry)
        session.add(subscription)
    order.status = OrderStatus.ACTIVE
    order.expires_at = expiry
    await session.commit()
    return subscription
