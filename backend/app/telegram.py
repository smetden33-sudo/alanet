import structlog
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .models import Customer, Plan, Subscription
from .services import create_checkout

settings = get_settings()
log = structlog.get_logger()
dispatcher = Dispatcher()
router = Router()
dispatcher.include_router(router)
email_adapter = TypeAdapter(EmailStr)
_bot: Bot | None = None


class CheckoutState(StatesGroup):
    email = State()


def get_bot() -> Bot:
    global _bot
    token = settings.telegram_bot_token.get_secret_value()
    if not token:
        raise RuntimeError("Telegram bot token is not configured")
    if _bot is None:
        _bot = Bot(token)
    return _bot


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Купить подписку", callback_data="buy")],
            [
                InlineKeyboardButton(text="Моя подписка", callback_data="subscription"),
                InlineKeyboardButton(text="Как подключиться", callback_data="setup"),
            ],
            [InlineKeyboardButton(text="Открыть сайт", url=settings.public_site_url)],
        ]
    )


def plans_menu(plans: list[Plan]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{plan.name} — {plan.price_rub:.0f} ₽",
                callback_data=f"plan:{plan.slug}",
            )
        ]
        for plan in plans
    ]
    rows.append([InlineKeyboardButton(text="Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def answer_callback(callback: CallbackQuery, text: str, **kwargs) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(text, **kwargs)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "ALANET — быстрый и безопасный доступ в интернет.\n\n"
        "Выберите тариф, получите ссылку подключения и используйте её на своих устройствах.",
        reply_markup=main_menu(),
    )


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Оформление отменено.", reply_markup=main_menu())


@router.callback_query(F.data == "menu")
async def show_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await answer_callback(callback, "Главное меню", reply_markup=main_menu())


@router.callback_query(F.data == "buy")
async def buy(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        plans = list(
            (await session.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.price_rub))).all()
        )
    if not plans:
        await answer_callback(callback, "Тарифы временно недоступны. Попробуйте немного позже.")
        return
    await answer_callback(
        callback,
        "Выберите тариф. Доступ включает все доступные серверы ALANET:",
        reply_markup=plans_menu(plans),
    )


@router.callback_query(F.data.startswith("plan:"))
async def select_plan(callback: CallbackQuery, state: FSMContext) -> None:
    slug = (callback.data or "").partition(":")[2]
    async with SessionLocal() as session:
        plan = await session.scalar(select(Plan).where(Plan.slug == slug, Plan.is_active.is_(True)))
    if not plan:
        await answer_callback(callback, "Этот тариф больше недоступен. Выберите другой.")
        return
    if not settings.yookassa_enabled:
        await answer_callback(
            callback,
            f"Тариф «{plan.name}» — {plan.price_rub:.0f} ₽.\n\n"
            "Онлайн-оплата сейчас подключается. Бот сообщит, когда оформление станет доступно.",
            reply_markup=main_menu(),
        )
        return
    await state.set_state(CheckoutState.email)
    await state.update_data(plan_slug=plan.slug)
    await answer_callback(
        callback,
        f"Вы выбрали «{plan.name}» за {plan.price_rub:.0f} ₽.\n\n"
        "Отправьте email для электронного чека. Для отмены используйте /cancel.",
    )


@router.message(CheckoutState.email)
async def checkout_email(message: Message, state: FSMContext) -> None:
    try:
        email = str(email_adapter.validate_python((message.text or "").strip()))
    except ValidationError:
        await message.answer("Не удалось распознать email. Проверьте адрес и отправьте ещё раз.")
        return
    data = await state.get_data()
    slug = str(data.get("plan_slug", ""))
    telegram_id = message.from_user.id if message.from_user else None
    telegram_username = f"@{message.from_user.username}" if message.from_user and message.from_user.username else None
    try:
        async with SessionLocal() as session:
            order, confirmation_url = await create_checkout(
                session,
                settings,
                plan_slug=slug,
                email=email,
                telegram_username=telegram_username,
                telegram_id=telegram_id,
            )
    except ValueError:
        await state.clear()
        await message.answer("Тариф недоступен. Начните оформление заново.", reply_markup=main_menu())
        return
    except Exception:
        log.exception("telegram_checkout_failed", telegram_id=telegram_id)
        await message.answer("Платёжный сервис временно недоступен. Попробуйте позже.")
        return
    await state.clear()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Оплатить", url=confirmation_url)]]
    )
    await message.answer(
        f"Заказ {order.id} создан. Нажмите кнопку ниже, чтобы перейти к безопасной оплате.",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "subscription")
async def subscription(callback: CallbackQuery) -> None:
    telegram_id = callback.from_user.id
    async with SessionLocal() as session:
        customer = await session.scalar(select(Customer).where(Customer.telegram_id == telegram_id))
        current = None
        if customer:
            current = await session.scalar(select(Subscription).where(Subscription.customer_id == customer.id))
    if not current:
        await answer_callback(
            callback,
            "Активная подписка не найдена. Если вы покупали доступ на сайте, обратитесь в поддержку для привязки.",
            reply_markup=main_menu(),
        )
        return
    expires = current.expires_at.astimezone().strftime("%d.%m.%Y %H:%M")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть подписку", url=current.subscription_url)],
            [InlineKeyboardButton(text="Главное меню", callback_data="menu")],
        ]
    )
    await answer_callback(
        callback,
        f"Подписка активна до {expires}.\n\nНе пересылайте персональную ссылку другим людям.",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "setup")
async def setup(callback: CallbackQuery) -> None:
    await answer_callback(
        callback,
        "1. Купите подписку и откройте персональную ссылку.\n"
        "2. Выберите приложение для Android, iOS, Windows или macOS.\n"
        "3. Импортируйте подписку и включите подключение.\n\n"
        "Если возникнет ошибка, откройте сайт и выберите раздел инструкций.",
        reply_markup=main_menu(),
    )
