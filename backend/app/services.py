import uuid
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from .config import Settings
from .integrations.remnawave import RemnawaveClient
from .integrations.yookassa import YooKassaClient
from .models import Customer, Order, OrderStatus, Payment, Plan, Subscription, SubscriptionStatus, TelegramBindToken, WebLoginToken, WebSession, WebhookEvent


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


async def create_web_login_link(session: AsyncSession, customer_id: uuid.UUID, settings: Settings) -> str:
    token = secrets.token_urlsafe(32)
    session.add(WebLoginToken(
        customer_id=customer_id,
        token_hash=_token_hash(token),
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    ))
    await session.flush()
    return f"{settings.public_site_url.rstrip('/')}/checkout/success?session={token}"


async def exchange_web_login_token(session: AsyncSession, token: str, settings: Settings) -> tuple[str, Customer]:
    login = await session.scalar(select(WebLoginToken).where(WebLoginToken.token_hash == _token_hash(token)).with_for_update())
    now = datetime.now(UTC)
    if not login or login.consumed_at or login.expires_at <= now:
        raise ValueError("login token is invalid or expired")
    customer = await session.get(Customer, login.customer_id, with_for_update=True)
    if not customer or customer.status.value != "ACTIVE":
        raise ValueError("customer is not active")
    session_token = secrets.token_urlsafe(48)
    session.add(WebSession(
        customer_id=customer.id,
        token_hash=_token_hash(session_token),
        expires_at=now + timedelta(days=settings.session_ttl_days),
    ))
    login.consumed_at = now
    await session.flush()
    return session_token, customer


async def get_web_session(session: AsyncSession, token: str) -> tuple[WebSession, Customer] | None:
    current = datetime.now(UTC)
    web_session = await session.scalar(select(WebSession).where(WebSession.token_hash == _token_hash(token)).with_for_update())
    if not web_session or web_session.revoked_at or web_session.expires_at <= current:
        return None
    customer = await session.get(Customer, web_session.customer_id)
    if not customer or customer.status.value != "ACTIVE":
        return None
    return web_session, customer


async def create_telegram_bind_token(session: AsyncSession, customer_id: uuid.UUID, settings: Settings) -> str:
    token = secrets.token_urlsafe(32)
    session.add(TelegramBindToken(
        customer_id=customer_id,
        token_hash=_token_hash(token),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    ))
    await session.flush()
    username = settings.telegram_bot_username.lstrip("@").strip()
    return f"https://t.me/{username}?start=bind_{token}"


async def bind_telegram_token(session: AsyncSession, token: str, telegram_id: int, telegram_username: str | None) -> Customer:
    row = await session.scalar(select(TelegramBindToken).where(TelegramBindToken.token_hash == _token_hash(token)).with_for_update())
    if not row or row.consumed_at or row.expires_at <= datetime.now(UTC):
        raise ValueError("bind token is invalid or expired")
    customer = await session.get(Customer, row.customer_id, with_for_update=True)
    if not customer:
        raise ValueError("customer not found")
    existing = await session.scalar(select(Customer).where(Customer.telegram_id == telegram_id).with_for_update())
    if existing and existing.id != customer.id:
        existing_subscription = await session.scalar(select(Subscription).where(Subscription.customer_id == existing.id).with_for_update())
        target_subscription = await session.scalar(select(Subscription).where(Subscription.customer_id == customer.id).with_for_update())
        if existing_subscription and target_subscription:
            raise ValueError("telegram account is already linked to another customer")
        orders = (await session.scalars(select(Order).where(Order.customer_id == existing.id))).all()
        for order in orders:
            order.customer_id = customer.id
        if existing_subscription:
            existing_subscription.customer_id = customer.id
        await session.execute(delete(TelegramBindToken).where(TelegramBindToken.customer_id == existing.id))
        await session.delete(existing)
    customer.telegram_id = telegram_id
    customer.telegram_username = telegram_username
    row.consumed_at = datetime.now(UTC)
    return customer


def extended_expiry(current: datetime | None, duration_days: int, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    base = current if current and current > now else now
    return base + timedelta(days=duration_days)


async def create_checkout(
    session: AsyncSession,
    settings: Settings,
    *,
    plan_slug: str,
    email: str,
    telegram_username: str | None,
    telegram_id: int | None = None,
) -> tuple[Order, str, str | None]:
    plan = await session.scalar(select(Plan).where(Plan.slug == plan_slug, Plan.is_active.is_(True)))
    if not plan:
        raise ValueError("unknown plan")
    email = normalize_email(email)
    customer = None
    if telegram_id is not None:
        customer = await session.scalar(select(Customer).where(Customer.telegram_id == telegram_id).with_for_update())
    if not customer:
        customer = await session.scalar(select(Customer).where(func.lower(Customer.email) == email).with_for_update())
    if customer:
        customer.email = email
        customer.telegram_username = telegram_username
    else:
        customer = Customer(email=email, telegram_username=telegram_username, telegram_id=telegram_id)
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
    bind_url = None
    if customer.telegram_id is None:
        bind_url = await create_telegram_bind_token(session, customer.id, settings)
        await session.commit()
    return order, result["confirmation"]["confirmation_url"], bind_url


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
        await client.update_user(
            subscription.remnawave_user_id,
            user_uuid=str(subscription.remnawave_legacy_uuid) if subscription.remnawave_legacy_uuid else None,
            expireAt=expiry.isoformat(),
            status="ACTIVE",
            trafficLimitBytes=plan.traffic_limit_bytes,
            hwidDeviceLimit=plan.device_limit,
            activeInternalSquads=[plan.remnawave_squad_id],
        )
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
