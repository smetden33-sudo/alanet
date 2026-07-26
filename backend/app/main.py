import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy.ext.asyncio import AsyncSession
from .config import get_settings
from .db import get_session
from .schemas import CheckoutRequest, CheckoutResponse
from .services import accept_yookassa_webhook, create_checkout

settings = get_settings()
log = structlog.get_logger()
app = FastAPI(title="Quiet Network Billing API", version="0.1.0", docs_url="/api/docs" if settings.environment != "production" else None)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
Instrumentator().instrument(app).expose(app, include_in_schema=False)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/checkout", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED)
async def checkout(data: CheckoutRequest, session: AsyncSession = Depends(get_session)) -> CheckoutResponse:
    if not settings.yookassa_enabled:
        raise HTTPException(status_code=503, detail="payment integration is not configured")
    try:
        order, url = await create_checkout(session, settings, plan_slug=data.plan_slug, email=str(data.email), telegram_username=data.telegram_username)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        log.exception("checkout_failed")
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
        raise HTTPException(status_code=503, detail="retry later")
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
