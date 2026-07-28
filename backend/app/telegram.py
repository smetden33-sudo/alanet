import uuid
import structlog
from datetime import UTC, datetime, timedelta
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, or_, select

from .config import get_settings
from .db import SessionLocal
from .integrations.remnawave import RemnawaveClient
from .models import AdminAction, AuditLog, Customer, Order, OrderStatus, Plan, Subscription, SubscriptionStatus
from .services import bind_telegram_token, create_checkout, create_web_login_link, extended_expiry, provision_order, retry_failed_provisioning

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
                InlineKeyboardButton(text="Личный кабинет", callback_data="account"),
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
    args = (message.text or "").split(maxsplit=1)
    if len(args) == 2 and args[1].strip().lower().startswith("bind_"):
        if not message.from_user:
            return
        try:
            async with SessionLocal() as session:
                customer = await bind_telegram_token(session, args[1].strip()[5:], message.from_user.id, f"@{message.from_user.username}" if message.from_user.username else None)
                session.add(AuditLog(actor=f"telegram:{message.from_user.id}", action="telegram_bind", entity="customer", entity_id=str(customer.id), details={"username": customer.telegram_username}))
                await session.commit()
            await message.answer("Telegram успешно привязан к вашему аккаунту. Теперь подписка будет отображаться в разделе «Моя подписка».", reply_markup=main_menu())
        except ValueError as exc:
            await message.answer("Ссылка привязки недействительна или уже использована. Если вы уже покупали доступ, обратитесь в поддержку.", reply_markup=main_menu())
        return
    if len(args) == 2 and args[1].strip().lower() == "trial":
        await send_trial(message)
        return
    await message.answer(
        "ALANET — быстрый и безопасный доступ в интернет.\n\n"
        "Выберите тариф, получите ссылку подключения и используйте её на своих устройствах.",
        reply_markup=main_menu(),
    )


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Оформление отменено.", reply_markup=main_menu())


async def issue_trial(telegram_id: int, telegram_username: str | None) -> tuple[Subscription | None, str]:
    async with SessionLocal() as session:
        customer = await session.scalar(select(Customer).where(Customer.telegram_id == telegram_id))
        if customer:
            current = await session.scalar(select(Subscription).where(Subscription.customer_id == customer.id))
            if current:
                return current, "Для этого Telegram-аккаунта ключ уже был создан. Откройте раздел «Моя подписка»."
        plan = await session.scalar(select(Plan).where(Plan.slug == "trial", Plan.is_active.is_(True)))
        if not plan:
            return None, "Пробный тариф временно недоступен."
        if not customer:
            customer = Customer(email=f"telegram-{telegram_id}@test.alanet.ru", telegram_id=telegram_id, telegram_username=telegram_username)
            session.add(customer)
            await session.flush()
        order = Order(customer_id=customer.id, plan_id=plan.id, amount=plan.price_rub, status=OrderStatus.PROVISIONING)
        session.add(order)
        await session.flush()
        try:
            subscription = await provision_order(session, settings, order.id)
        except Exception:
            log.exception("telegram_test_provisioning_failed", telegram_id=telegram_id)
            await session.rollback()
            return None, "Не удалось создать пробный доступ. Попробуйте ещё раз позже."
        session.add(AuditLog(actor=f"telegram:{telegram_id}", action="telegram_test_claim", entity="subscription", entity_id=str(subscription.id), details={"username": telegram_username}))
        await session.commit()
    return subscription, "Пробный доступ создан на 24 часа. В подписке доступна 1 локация."


async def send_trial(message: Message) -> None:
    if not message.from_user:
        return
    username = f"@{message.from_user.username}" if message.from_user.username else None
    subscription, text = await issue_trial(message.from_user.id, username)
    keyboard = None
    if subscription:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть подписку", url=subscription.subscription_url)]])
    await message.answer(text, reply_markup=keyboard)


@router.message(Command("test"))
async def test_access(message: Message) -> None:
    await send_trial(message)


async def send_account_link(message: Message) -> None:
    if not message.from_user:
        return
    async with SessionLocal() as session:
        customer = await session.scalar(select(Customer).where(Customer.telegram_id == message.from_user.id))
        if not customer:
            await message.answer("Сначала получите пробный доступ или оформите подписку, затем кабинет станет доступен.", reply_markup=main_menu())
            return
        link = await create_web_login_link(session, customer.id, settings)
        await session.commit()
    await message.answer("Ваша защищённая ссылка в личный кабинет действует 15 минут и может быть использована один раз.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть личный кабинет", url=link)], [InlineKeyboardButton(text="Главное меню", callback_data="menu")]]))


@router.message(Command("account"))
async def account_command(message: Message) -> None:
    await send_account_link(message)


def is_admin(message: Message) -> bool:
    return bool(
        message.from_user
        and settings.telegram_admin_chat_id is not None
        and message.from_user.id == settings.telegram_admin_chat_id
    )


async def require_admin(message: Message) -> bool:
    if is_admin(message):
        return True
    await message.answer("Команда доступна только администратору.")
    return False


def command_args(message: Message) -> list[str]:
    return (message.text or "").split()[1:]


async def find_customer(session, target: str) -> Customer | None:
    conditions = [Customer.telegram_username.ilike(target)]
    if target.isdigit():
        conditions.append(Customer.telegram_id == int(target))
    if "@" in target or "." in target:
        conditions.append(Customer.email.ilike(target))
    try:
        remnawave_uuid = uuid.UUID(target)
        conditions.append(Customer.id.in_(select(Subscription.customer_id).where(Subscription.remnawave_legacy_uuid == remnawave_uuid)))
    except ValueError:
        pass
    return await session.scalar(select(Customer).where(or_(*conditions)))


async def request_admin_action(message: Message, action: str, target: str, payload: dict, description: str) -> None:
    pending = AdminAction(
        admin_telegram_id=message.from_user.id,
        action=action,
        target=target,
        payload=payload,
        status="PENDING",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        result={},
    )
    async with SessionLocal() as session:
        session.add(pending)
        await session.flush()
        session.add(AuditLog(actor=f"admin:{message.from_user.id}", action=f"admin_{action}_requested", entity="admin_action", entity_id=str(pending.id), details={"target": target, "payload": payload}))
        await session.commit()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить", callback_data=f"admin_action:confirm:{pending.id}"), InlineKeyboardButton(text="Отмена", callback_data=f"admin_action:cancel:{pending.id}")]
    ])
    await message.answer(f"Требуется подтверждение.\n{description}\nЗапрос действует 10 минут.", reply_markup=keyboard)


async def execute_admin_action(action_id: uuid.UUID, admin_id: int) -> str:
    async with SessionLocal() as session:
        pending = await session.scalar(select(AdminAction).where(AdminAction.id == action_id).with_for_update())
        if not pending or pending.admin_telegram_id != admin_id:
            return "Действие не найдено."
        if pending.status != "PENDING":
            return f"Действие уже обработано: {pending.status}."
        if pending.expires_at <= datetime.now(UTC):
            pending.status = "EXPIRED"
            await session.commit()
            return "Срок подтверждения истёк. Повторите команду."
        pending.status = "EXECUTING"
        await session.commit()
        previous: dict = {}
        updated: dict = {}
        try:
            if pending.action == "grant":
                telegram_id = int(pending.target)
                slug = str(pending.payload["plan"])
                customer = await session.scalar(select(Customer).where(Customer.telegram_id == telegram_id))
                plan = await session.scalar(select(Plan).where(Plan.slug == slug, Plan.is_active.is_(True)))
                if not plan:
                    raise ValueError("активный тариф не найден")
                if not customer:
                    customer = Customer(email=f"telegram-{telegram_id}@admin.alanet.ru", telegram_id=telegram_id)
                    session.add(customer)
                    await session.flush()
                current = await session.scalar(select(Subscription).where(Subscription.customer_id == customer.id))
                previous = {"subscription_status": current.status.value, "expires_at": current.expires_at.isoformat()} if current else {"subscription_status": None}
                order = Order(customer_id=customer.id, plan_id=plan.id, amount=0, status=OrderStatus.PROVISIONING)
                session.add(order)
                await session.flush()
                subscription = await provision_order(session, settings, order.id)
                updated = {"subscription_status": subscription.status.value, "expires_at": subscription.expires_at.isoformat(), "plan": slug}
                response = f"Тариф {plan.name} выдан клиенту {telegram_id} до {subscription.expires_at.astimezone().strftime('%d.%m.%Y %H:%M')}\n{subscription.subscription_url}"
            elif pending.action == "extend":
                telegram_id = int(pending.target)
                days = int(pending.payload["days"])
                customer = await session.scalar(select(Customer).where(Customer.telegram_id == telegram_id))
                subscription = await session.scalar(select(Subscription).where(Subscription.customer_id == customer.id)) if customer else None
                if not subscription:
                    raise ValueError("подписка не найдена")
                previous = {"subscription_status": subscription.status.value, "expires_at": subscription.expires_at.isoformat()}
                expiry = extended_expiry(subscription.expires_at, days)
                await RemnawaveClient(settings).update_user(subscription.remnawave_user_id, user_uuid=str(subscription.remnawave_legacy_uuid) if subscription.remnawave_legacy_uuid else None, expireAt=expiry.isoformat(), status="ACTIVE")
                subscription.expires_at = expiry
                subscription.status = SubscriptionStatus.ACTIVE
                await session.commit()
                updated = {"subscription_status": subscription.status.value, "expires_at": expiry.isoformat(), "days": days}
                response = f"Подписка клиента {telegram_id} продлена до {expiry.astimezone().strftime('%d.%m.%Y %H:%M')}."
            elif pending.action == "revoke":
                telegram_id = int(pending.target)
                customer = await session.scalar(select(Customer).where(Customer.telegram_id == telegram_id))
                subscription = await session.scalar(select(Subscription).where(Subscription.customer_id == customer.id)) if customer else None
                if not subscription:
                    raise ValueError("подписка не найдена")
                previous = {"subscription_status": subscription.status.value, "expires_at": subscription.expires_at.isoformat()}
                await RemnawaveClient(settings).revoke_subscription(subscription.remnawave_user_id)
                subscription.status = SubscriptionStatus.DISABLED
                await session.commit()
                updated = {"subscription_status": subscription.status.value, "expires_at": subscription.expires_at.isoformat()}
                response = f"Подписка клиента {telegram_id} отозвана."
            else:
                raise ValueError("неизвестное административное действие")
            pending = await session.get(AdminAction, action_id, with_for_update=True)
            pending.status = "COMPLETED"
            pending.executed_at = datetime.now(UTC)
            pending.result = updated
            session.add(AuditLog(actor=f"admin:{admin_id}", action=f"admin_{pending.action}", entity="admin_action", entity_id=str(pending.id), details={"target": pending.target, "previous": previous, "updated": updated, "result": "success"}))
            await session.commit()
            return response
        except Exception as exc:
            await session.rollback()
            pending = await session.get(AdminAction, action_id, with_for_update=True)
            if pending:
                pending.status = "FAILED"
                pending.executed_at = datetime.now(UTC)
                pending.result = {"error": type(exc).__name__}
                session.add(AuditLog(actor=f"admin:{admin_id}", action=f"admin_{pending.action}", entity="admin_action", entity_id=str(pending.id), details={"target": pending.target, "previous": previous, "updated": updated, "result": "failed", "error": type(exc).__name__}))
                await session.commit()
            log.exception("admin_action_failed", action_id=str(action_id))
            return f"Действие не выполнено: {exc}"


@router.callback_query(F.data.startswith("admin_action:"))
async def admin_action_callback(callback: CallbackQuery) -> None:
    if callback.from_user.id != settings.telegram_admin_chat_id:
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    parts = (callback.data or "").split(":", 2)
    if len(parts) != 3:
        await callback.answer("Некорректная команда", show_alert=True)
        return
    operation, raw_id = parts[1], parts[2]
    try:
        action_id = uuid.UUID(raw_id)
    except ValueError:
        await callback.answer("Некорректный идентификатор", show_alert=True)
        return
    await callback.answer()
    if operation == "cancel":
        async with SessionLocal() as session:
            pending = await session.scalar(select(AdminAction).where(AdminAction.id == action_id).with_for_update())
            if not pending or pending.admin_telegram_id != callback.from_user.id or pending.status != "PENDING":
                text = "Действие уже обработано или не найдено."
            else:
                pending.status = "CANCELED"
                pending.executed_at = datetime.now(UTC)
                session.add(AuditLog(actor=f"admin:{callback.from_user.id}", action=f"admin_{pending.action}_canceled", entity="admin_action", entity_id=str(pending.id), details={"target": pending.target}))
                await session.commit()
                text = "Действие отменено."
    elif operation == "confirm":
        text = await execute_admin_action(action_id, callback.from_user.id)
    else:
        text = "Неизвестная операция."
    if callback.message:
        await callback.message.answer(text)


def customer_label(customer: Customer) -> str:
    return customer.telegram_username or str(customer.telegram_id or customer.email)


@router.message(Command("admin"))
async def admin_menu(message: Message) -> None:
    if not await require_admin(message):
        return
    await message.answer(
        "Административное меню\n\n"
        "/stats — статистика клиентов и подписок\n"
        "/user <telegram_id|@username|email> — карточка клиента\n"
        "/grant <telegram_id> <trial|start|calm|year> — выдать тариф\n"
        "/extend <telegram_id> <дни> — продлить подписку\n"
        "/revoke <telegram_id> — отозвать подписку\n"
        "/nodes — состояние нод Remnawave\n"
        "/orders [STATUS|all] [дни] — фильтр заказов\n"
        "/retry <order_id> — повторить неудачную выдачу"
    )


@router.message(Command("stats"))
async def admin_stats(message: Message) -> None:
    if not await require_admin(message):
        return
    async with SessionLocal() as session:
        customers = await session.scalar(select(func.count()).select_from(Customer))
        active = await session.scalar(select(func.count()).select_from(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE))
        orders = await session.scalar(select(func.count()).select_from(Order))
        paid = await session.scalar(select(func.count()).select_from(Order).where(Order.status == OrderStatus.ACTIVE, Order.amount > 0))
    await message.answer(
        f"Статистика\n\nКлиентов: {customers}\nАктивных подписок: {active}\nВсего заказов: {orders}\nАктивных платных заказов: {paid}"
    )


@router.message(Command("user"))
async def admin_user(message: Message) -> None:
    if not await require_admin(message):
        return
    args = command_args(message)
    if len(args) != 1:
        await message.answer("Использование: /user <telegram_id|@username|email>")
        return
    async with SessionLocal() as session:
        customer = await find_customer(session, args[0])
        if not customer:
            await message.answer("Клиент не найден.")
            return
        subscription = await session.scalar(select(Subscription).where(Subscription.customer_id == customer.id))
        last_order = await session.scalar(select(Order).where(Order.customer_id == customer.id).order_by(Order.created_at.desc()))
    lines = [
        f"Клиент: {customer_label(customer)}",
        f"Telegram ID: {customer.telegram_id or '—'}",
        f"Email: {customer.email}",
        f"Статус: {customer.status.value}",
    ]
    if subscription:
        lines.extend([
            f"Подписка: {subscription.status.value}",
            f"Действует до: {subscription.expires_at.astimezone().strftime('%d.%m.%Y %H:%M')}",
            f"Ссылка: {subscription.subscription_url}",
            f"Remnawave ID: {subscription.remnawave_user_id}",
        ])
    else:
        lines.append("Подписка: отсутствует")
    if last_order:
        lines.append(f"Последний заказ: {last_order.status.value}, {last_order.amount:.2f} ₽")
    await message.answer("\n".join(lines))


@router.message(Command("grant"))
async def admin_grant(message: Message) -> None:
    if not await require_admin(message):
        return
    args = command_args(message)
    if len(args) != 2:
        await message.answer("Использование: /grant <telegram_id> <trial|start|calm|year>")
        return
    target, slug = args
    if not target.isdigit():
        await message.answer("Для выдачи нужен числовой Telegram ID.")
        return
    async with SessionLocal() as session:
        plan = await session.scalar(select(Plan).where(Plan.slug == slug, Plan.is_active.is_(True)))
    if not plan:
        await message.answer("Активный тариф не найден.")
        return
    await request_admin_action(message, "grant", target, {"plan": slug}, f"Выдать тариф «{plan.name}» клиенту Telegram ID {target}.")


@router.message(Command("extend"))
async def admin_extend(message: Message) -> None:
    if not await require_admin(message):
        return
    args = command_args(message)
    if len(args) != 2 or not args[0].isdigit() or not args[1].isdigit():
        await message.answer("Использование: /extend <telegram_id> <дни>")
        return
    days = int(args[1])
    if days < 1 or days > 3650:
        await message.answer("Количество дней должно быть от 1 до 3650.")
        return
    async with SessionLocal() as session:
        customer = await session.scalar(select(Customer).where(Customer.telegram_id == int(args[0])))
        subscription = await session.scalar(select(Subscription).where(Subscription.customer_id == customer.id)) if customer else None
    if not subscription:
        await message.answer("Активная подписка не найдена.")
        return
    await request_admin_action(message, "extend", args[0], {"days": days}, f"Продлить подписку Telegram ID {args[0]} на {days} дней. Текущая дата окончания: {subscription.expires_at.astimezone().strftime('%d.%m.%Y %H:%M')}.")


@router.message(Command("revoke"))
async def admin_revoke(message: Message) -> None:
    if not await require_admin(message):
        return
    args = command_args(message)
    if len(args) != 1 or not args[0].isdigit():
        await message.answer("Использование: /revoke <telegram_id>")
        return
    async with SessionLocal() as session:
        customer = await session.scalar(select(Customer).where(Customer.telegram_id == int(args[0])))
        subscription = await session.scalar(select(Subscription).where(Subscription.customer_id == customer.id)) if customer else None
    if not subscription:
        await message.answer("Подписка не найдена.")
        return
    await request_admin_action(message, "revoke", args[0], {}, f"Отозвать подписку Telegram ID {args[0]}. Доступ будет отключён сразу.")


@router.message(Command("nodes"))
async def admin_nodes(message: Message) -> None:
    if not await require_admin(message):
        return
    try:
        nodes = await RemnawaveClient(settings).list_nodes()
    except Exception:
        log.exception("admin_nodes_failed")
        await message.answer("Не удалось получить состояние нод Remnawave.")
        return
    if not nodes:
        await message.answer("Ноды не найдены.")
        return
    lines = ["Ноды Remnawave:"]
    for node in nodes:
        state = "подключена" if node.get("isConnected") else "не подключена"
        lines.append(f"{node.get('name', '—')}: {state}, {node.get('countryCode') or '—'}")
    await message.answer("\n".join(lines))


@router.message(Command("orders"))
async def admin_orders(message: Message) -> None:
    if not await require_admin(message):
        return
    args = command_args(message)
    if len(args) > 2:
        await message.answer("Использование: /orders [STATUS|all] [дни]")
        return
    status_filter = args[0].upper() if args else "ALL"
    if status_filter != "ALL" and status_filter not in OrderStatus.__members__:
        await message.answer("Неизвестный статус. Пример: /orders PROVISIONING_FAILED 7")
        return
    try:
        days = int(args[1]) if len(args) == 2 else 30
    except ValueError:
        await message.answer("Период должен быть числом дней.")
        return
    if days < 1 or days > 365:
        await message.answer("Период должен быть от 1 до 365 дней.")
        return
    query = select(Order, Plan, Customer).join(Plan, Plan.id == Order.plan_id).join(Customer, Customer.id == Order.customer_id).where(Order.created_at >= datetime.now(UTC) - timedelta(days=days))
    if status_filter != "ALL":
        query = query.where(Order.status == OrderStatus[status_filter])
    query = query.order_by(Order.created_at.desc()).limit(20)
    async with SessionLocal() as session:
        rows = (await session.execute(query)).all()
    if not rows:
        await message.answer("Заказов пока нет.")
        return
    lines = [f"Заказы: статус {status_filter}, период {days} дн."]
    for order, plan, customer in rows:
        created = order.created_at.astimezone().strftime("%d.%m %H:%M") if order.created_at else "—"
        lines.append(f"{created} · {customer_label(customer)} · {plan.name} · {order.status.value} · {order.amount:.2f} ₽")
    await message.answer("\n".join(lines))


@router.message(Command("retry"))
async def admin_retry_provisioning(message: Message) -> None:
    if not await require_admin(message):
        return
    args = command_args(message)
    if len(args) != 1:
        await message.answer("Использование: /retry <order_id>")
        return
    try:
        order_id = uuid.UUID(args[0])
    except ValueError:
        await message.answer("Некорректный UUID заказа.")
        return
    async with SessionLocal() as session:
        order = await session.get(Order, order_id)
        if not order:
            await message.answer("Заказ не найден.")
            return
        previous_status = order.status.value
        try:
            subscription = await retry_failed_provisioning(session, settings, order_id)
        except ValueError as exc:
            await message.answer(f"Повтор невозможен: {exc}")
            return
        except Exception:
            log.exception("admin_retry_provisioning_failed", order_id=str(order_id))
            await message.answer("Повтор provisioning не удался. Заказ сохранён для следующей попытки.")
            return
        session.add(AuditLog(actor=f"admin:{message.from_user.id}", action="admin_retry_provisioning", entity="order", entity_id=str(order_id), details={"previous_status": previous_status, "new_status": OrderStatus.ACTIVE.value}))
        await session.commit()
    await message.answer(f"Provisioning завершён. Подписка активна до {subscription.expires_at.astimezone().strftime('%d.%m.%Y %H:%M')}.\n{subscription.subscription_url}")


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
        "Выберите тариф. Платные планы включают все серверы ALANET, пробный — 1 локация:",
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
    if plan.slug == "trial":
        username = f"@{callback.from_user.username}" if callback.from_user.username else None
        subscription, text = await issue_trial(callback.from_user.id, username)
        keyboard = main_menu()
        if subscription:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Открыть подписку", url=subscription.subscription_url)],
                    [InlineKeyboardButton(text="Главное меню", callback_data="menu")],
                ]
            )
        await answer_callback(callback, text, reply_markup=keyboard)
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
            order, confirmation_url, _bind_url = await create_checkout(
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


@router.callback_query(F.data == "account")
async def account_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    await callback.answer()
    await send_account_link(callback.message)


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
