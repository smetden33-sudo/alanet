from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from .config import get_settings

settings = get_settings()
bot = Bot(settings.telegram_bot_token.get_secret_value())
dispatcher = Dispatcher()
router = Router()
dispatcher.include_router(router)


def menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Моя подписка", callback_data="subscription"), InlineKeyboardButton(text="Подключить устройство", callback_data="setup")],
        [InlineKeyboardButton(text="Инструкции", callback_data="help"), InlineKeyboardButton(text="Поддержка", url="https://t.me/your_support")],
    ])


@router.message(CommandStart())
async def start(message: Message) -> None:
    token = (message.text or "").partition(" ")[2]
    if token.startswith("bind_"):
        await message.answer("Привязка получена. Одноразовый токен будет проверен сервером.")
    await message.answer("Здесь можно получить ссылку, проверить срок и подключить новое устройство.", reply_markup=menu())


@router.callback_query(F.data == "subscription")
async def subscription(callback) -> None:
    await callback.answer()
    await callback.message.answer("Подписка появится здесь после оплаты и привязки аккаунта.")


@router.callback_query(F.data == "setup")
async def setup(callback) -> None:
    await callback.answer()
    await callback.message.answer("Выберите инструкцию для Android, iOS, Windows или macOS на странице подписки.")


@router.callback_query(F.data == "help")
async def help_callback(callback) -> None:
    await callback.answer()
    await callback.message.answer("Откройте ссылку подписки в рекомендованном приложении. Если не получится — напишите в поддержку.")
