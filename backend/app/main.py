import structlog
import asyncio
import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from .config import get_settings
from .db import get_session
from .models import AuditLog, Customer, Order, OrderStatus, Payment, Plan, Subscription, SubscriptionStatus
from .remnawave_registry import load_node_registry
from .notifications import notify_admin
from .schemas import CheckoutRequest, CheckoutResponse, RenewalCheckoutRequest, TelegramSessionExchangeRequest
from .services import accept_yookassa_webhook, create_checkout, exchange_web_login_token, get_web_session

settings = get_settings()
log = structlog.get_logger()
app = FastAPI(title="Quiet Network Billing API", version="0.1.0", docs_url="/api/docs" if settings.environment != "production" else None)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
Instrumentator().instrument(app).expose(app, include_in_schema=False)
rate_buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)
rate_lock = asyncio.Lock()
rate_limits = {
    "/api/v1/checkout": (10, 60),
    "/api/v1/me/checkout": (10, 60),
    "/api/v1/auth/telegram/exchange": (10, 60),
    "/webhooks/yookassa": (120, 60),
    "/webhooks/telegram": (300, 60),
}


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    limit = rate_limits.get(request.url.path)
    if limit:
        forwarded = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded.split(",", 1)[0].strip() or (request.client.host if request.client else "unknown")
        maximum, window = limit
        now = time.monotonic()
        key = (request.url.path, client_ip)
        async with rate_lock:
            bucket = rate_buckets[key]
            while bucket and bucket[0] <= now - window:
                bucket.popleft()
            if len(bucket) >= maximum:
                return Response(status_code=429, content='{"detail":"too many requests"}', media_type="application/json", headers={"Retry-After": str(window)})
            bucket.append(now)
    return await call_next(request)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/status")
async def public_status(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    checked_at = datetime.now(UTC).isoformat()
    services: list[dict[str, object]] = [
        {"name": "api", "status": "ok", "detail": "health endpoint is available"},
    ]
    try:
        customers = await session.scalar(select(func.count()).select_from(Customer)) or 0
        active_subscriptions = await session.scalar(select(func.count()).select_from(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE)) or 0
        active_orders = await session.scalar(select(func.count()).select_from(Order).where(Order.status == OrderStatus.ACTIVE)) or 0
        succeeded_payments = await session.scalar(select(func.count()).select_from(Payment).where(Payment.status == "succeeded")) or 0
        failed_orders = await session.scalar(select(func.count()).select_from(Order).where(Order.status == OrderStatus.PROVISIONING_FAILED)) or 0
        services.append(
            {
                "name": "billing-db",
                "status": "ok",
                "detail": f"customers={customers}, active_subscriptions={active_subscriptions}, active_orders={active_orders}, succeeded_payments={succeeded_payments}, failed_orders={failed_orders}",
            }
        )
    except Exception:
        log.exception("public_status_db_failed")
        services.append({"name": "billing-db", "status": "degraded", "detail": "database check failed"})

    try:
        registry = load_node_registry()
        nodes = registry.get("nodes") or []
        active_nodes = sum(1 for node in nodes if node.get("status") == "active")
        services.append(
            {
                "name": "node-registry",
                "status": "ok",
                "detail": f"active_nodes={active_nodes}, total_nodes={len(nodes)}",
            }
        )
    except Exception:
        log.exception("public_status_registry_failed")
        services.append({"name": "node-registry", "status": "degraded", "detail": "registry file unavailable"})

    services.append(
        {
            "name": "payments",
            "status": "ok" if settings.yookassa_enabled else "degraded",
            "detail": "YooKassa enabled" if settings.yookassa_enabled else "YooKassa is not configured",
        }
    )
    services.append(
        {
            "name": "telegram",
            "status": "ok" if settings.telegram_webhook_secret.get_secret_value() else "degraded",
            "detail": "webhook secret configured" if settings.telegram_webhook_secret.get_secret_value() else "webhook secret missing",
        }
    )

    overall = "ok" if all(service["status"] == "ok" for service in services) else "degraded"
    return {"status": overall, "checked_at": checked_at, "services": services}


def session_cookie_kwargs() -> dict:
    return {"key": "alanet_session", "httponly": True, "secure": settings.environment == "production", "samesite": "lax", "domain": settings.session_cookie_domain or None, "max_age": settings.session_ttl_days * 86400, "path": "/"}


async def current_web_customer(request: Request, session: AsyncSession) -> tuple[object, Customer]:
    token = request.cookies.get("alanet_session")
    if not token:
        raise HTTPException(status_code=401, detail="authentication required")
    current = await get_web_session(session, token)
    if not current:
        raise HTTPException(status_code=401, detail="session expired")
    return current


@app.post("/api/v1/auth/telegram/exchange")
async def exchange_telegram_session(data: TelegramSessionExchangeRequest, response: Response, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    try:
        web_token, customer = await exchange_web_login_token(session, data.token, settings)
        session.add(AuditLog(actor=f"customer:{customer.id}", action="web_login", entity="customer", entity_id=str(customer.id), details={"method": "telegram"}))
        await session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="login link is invalid or expired") from exc
    response.set_cookie(value=web_token, **session_cookie_kwargs())
    return {"ok": True}


@app.get("/api/v1/me")
async def me(request: Request, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    _, customer = await current_web_customer(request, session)
    subscription = await session.scalar(select(Subscription).where(Subscription.customer_id == customer.id))
    plan = None
    if subscription:
        plan = await session.scalar(select(Plan).join(Order, Order.plan_id == Plan.id).where(Order.customer_id == customer.id, Order.status == OrderStatus.ACTIVE).order_by(Order.created_at.desc()))
    return {"customer": {"email": customer.email, "telegram_username": customer.telegram_username}, "subscription": ({"status": subscription.status.value, "expires_at": subscription.expires_at.isoformat(), "subscription_url": subscription.subscription_url, "plan": plan.name if plan else "Подписка", "locations": "1 локация — ALANET-CZ-1" if plan and plan.slug == "trial" else "Все доступные локации"} if subscription else None)}


@app.get("/api/v1/orders/{order_id}")
async def order_status(order_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    order = await session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order not found")
    subscription = await session.scalar(select(Subscription).where(Subscription.customer_id == order.customer_id)) if order.status == OrderStatus.ACTIVE else None
    return {"status": order.status.value, "subscription_url": subscription.subscription_url if subscription else None, "expires_at": subscription.expires_at.isoformat() if subscription else None}


@app.post("/api/v1/auth/logout")
async def logout(request: Request, response: Response, session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    token = request.cookies.get("alanet_session")
    if token:
        current = await get_web_session(session, token)
        if current:
            current[0].revoked_at = datetime.now(UTC)
            await session.commit()
    response.delete_cookie("alanet_session", domain=settings.session_cookie_domain or None, path="/")
    return {"ok": True}


@app.post("/api/v1/checkout", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED)
async def checkout(data: CheckoutRequest, session: AsyncSession = Depends(get_session)) -> CheckoutResponse:
    if not settings.yookassa_enabled:
        raise HTTPException(status_code=503, detail="payment integration is not configured")
    try:
        order, url, bind_url = await create_checkout(session, settings, plan_slug=data.plan_slug, email=str(data.email), telegram_username=data.telegram_username)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        log.exception("checkout_failed")
        raise HTTPException(status_code=503, detail="payment provider unavailable")
    return CheckoutResponse(order_id=str(order.id), confirmation_url=url, telegram_bind_url=bind_url)


@app.post("/api/v1/me/checkout", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED)
async def authenticated_checkout(data: RenewalCheckoutRequest, request: Request, session: AsyncSession = Depends(get_session)) -> CheckoutResponse:
    if not settings.yookassa_enabled:
        raise HTTPException(status_code=503, detail="payment integration is not configured")
    _, customer = await current_web_customer(request, session)
    if customer.telegram_id is None:
        raise HTTPException(status_code=409, detail="telegram account is not linked")
    try:
        order, url, _ = await create_checkout(
            session,
            settings,
            plan_slug=data.plan_slug,
            email=customer.email,
            telegram_username=customer.telegram_username,
            telegram_id=customer.telegram_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        log.exception("authenticated_checkout_failed", customer_id=str(customer.id))
        raise HTTPException(status_code=503, detail="payment provider unavailable")
    return CheckoutResponse(order_id=str(order.id), confirmation_url=url)


@app.post("/webhooks/yookassa")
async def yookassa_webhook(request: Request, session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    if not settings.yookassa_enabled:
        raise HTTPException(status_code=503, detail="payment integration is not configured")
    payload = await request.json()
    try:
        result = await accept_yookassa_webhook(session, settings, payload)
    except ValueError as exc:
        log.warning("invalid_yookassa_webhook", reason=str(exc))
        raise HTTPException(status_code=400, detail="invalid notification") from exc
    except Exception:
        log.exception("yookassa_webhook_failed")
        payment_id = str(payload.get("object", {}).get("id", ""))
        await notify_admin(settings, f"ALANET: ошибка обработки подтверждённого платежа. Payment ID: {payment_id or 'не указан'}. Заказ сохранён для повторной обработки.")
        raise HTTPException(status_code=503, detail="retry later")
    if result == "processed":
        payment_id = str(payload.get("object", {}).get("id", ""))
        await notify_admin(settings, f"ALANET: платёж успешно обработан и подписка активирована. Payment ID: {payment_id}.")
    return {"status": result}


@app.post("/webhooks/telegram")
async def telegram_webhook(request: Request) -> dict[str, bool]:
    supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    expected = settings.telegram_webhook_secret.get_secret_value()
    if not expected or supplied != expected:
        raise HTTPException(status_code=403, detail="forbidden")
    from .telegram import dispatcher, get_bot
    from aiogram.types import Update
    bot = get_bot()
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dispatcher.feed_update(bot, update)
    return {"ok": True}
