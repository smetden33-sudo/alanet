import httpx
import structlog

from .config import Settings


log = structlog.get_logger()


async def send_telegram_message(settings: Settings, chat_id: int, text: str) -> bool:
    token = settings.telegram_bot_token.get_secret_value()
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            )
        response.raise_for_status()
        return True
    except Exception:
        log.exception("telegram_notification_failed", chat_id=chat_id)
        return False


async def notify_admin(settings: Settings, text: str) -> bool:
    if settings.telegram_admin_chat_id is None:
        return False
    return await send_telegram_message(settings, settings.telegram_admin_chat_id, text)
