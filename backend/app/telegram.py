import uuid
import asyncio
import json
import structlog
from datetime import UTC, datetime, timedelta
from pathlib import Path
import httpx
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, or_, select

from .config import get_settings
from .db import SessionLocal
from .financial_reconciliation import reconcile_yookassa_finance
from .integrations.remnawave import RemnawaveClient
from .models import AdminAction, AuditLog, Customer, Order, OrderStatus, Payment, Plan, Subscription, SubscriptionStatus
from .notifications import notify_admin
from .remnawave_registry import compare_registry_to_remnawave, load_node_registry, summarize_drift
from .services import bind_telegram_token, create_checkout, extended_expiry, provision_order, retry_failed_provisioning

settings = get_settings()
log = structlog.get_logger()
dispatcher = Dispatcher()
router = Router()
dispatcher.include_router(router)
_bot: Bot | None = None


def get_bot() -> Bot:
    global _bot
    token = settings.telegram_bot_token.get_secret_value()
    if not token:
        raise RuntimeError("Telegram bot token is not configured")
    if _bot is None:
        _bot = Bot(token)
    return _bot


async def register_bot_commands() -> None:
    bot = get_bot()
    public_commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="test", description="Пробный доступ на 24 часа"),
        BotCommand(command="cancel", description="Отменить действие"),
    ]
    admin_commands = [
        *public_commands,
        BotCommand(command="admin", description="Административное меню"),
        BotCommand(command="stats", description="Статистика сервиса"),
        BotCommand(command="status", description="Короткий статус проекта"),
        BotCommand(command="incident", description="Карточка incident mode"),
        BotCommand(command="health", description="Полная диагностика"),
        BotCommand(command="ports", description="Проверка портов нод"),
        BotCommand(command="backup", description="Статус backup"),
        BotCommand(command="disk", description="Диск prod"),
        BotCommand(command="cleanup", description="Статус автоочистки prod"),
        BotCommand(command="deploy_status", description="Версия deploy"),
        BotCommand(command="node_backup", description="Backup нод"),
        BotCommand(command="failed", description="Что требует внимания"),
        BotCommand(command="risk", description="Карта рисков"),
        BotCommand(command="payments", description="Последние оплаты"),
        BotCommand(command="finance", description="Сверка YooKassa"),
        BotCommand(command="user", description="Карточка пользователя"),
        BotCommand(command="grant", description="Выдать доступ"),
        BotCommand(command="extend", description="Продлить доступ"),
        BotCommand(command="revoke", description="Отозвать доступ"),
        BotCommand(command="nodes", description="Список нод"),
        BotCommand(command="node", description="Карточка ноды"),
        BotCommand(command="orders", description="Последние заказы"),
        BotCommand(command="retry_failed", description="Повторить failed provisioning"),
        BotCommand(command="audit", description="Журнал действий"),
        BotCommand(command="remnawave_sync", description="Drift Remnawave"),
    ]

    await bot.set_my_commands(public_commands, scope=BotCommandScopeDefault())
    await bot.set_my_commands(public_commands, scope=BotCommandScopeAllPrivateChats())
    for admin_id in admin_roles():
        await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))


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


def is_admin(message: Message) -> bool:
    return bool(message.from_user and admin_role_for_user(message.from_user.id) is not None)


def parse_telegram_id_list(raw: str) -> set[int]:
    result: set[int] = set()
    for item in (raw or "").replace(";", ",").split(","):
        value = item.strip()
        if not value:
            continue
        try:
            result.add(int(value))
        except ValueError:
            log.warning("invalid_telegram_admin_id", value=value)
    return result


def admin_roles() -> dict[int, str]:
    roles: dict[int, str] = {}
    for telegram_id in parse_telegram_id_list(settings.telegram_readonly_ids):
        roles[telegram_id] = "readonly"
    for telegram_id in parse_telegram_id_list(settings.telegram_support_ids):
        roles[telegram_id] = "support"
    for telegram_id in parse_telegram_id_list(settings.telegram_admin_ids):
        roles[telegram_id] = "admin"
    for telegram_id in parse_telegram_id_list(settings.telegram_owner_ids):
        roles[telegram_id] = "owner"
    if settings.telegram_admin_chat_id is not None:
        roles[settings.telegram_admin_chat_id] = "owner"
    return roles


ROLE_PERMISSIONS = {
    "readonly": {"read"},
    "support": {"read", "audit"},
    "admin": {"read", "audit", "billing", "provision", "ops"},
    "owner": {"read", "audit", "billing", "provision", "ops", "revoke", "owner"},
}


ADMIN_ACTION_PERMISSIONS = {
    "grant": "provision",
    "extend": "provision",
    "revoke": "revoke",
}


def admin_role_for_user(telegram_id: int | None) -> str | None:
    if telegram_id is None:
        return None
    return admin_roles().get(telegram_id)


def has_admin_permission(telegram_id: int | None, permission: str = "read") -> bool:
    role = admin_role_for_user(telegram_id)
    if role is None:
        return False
    return permission in ROLE_PERMISSIONS.get(role, set())


async def require_admin(message: Message, permission: str = "read") -> bool:
    telegram_id = message.from_user.id if message.from_user else None
    if has_admin_permission(telegram_id, permission):
        return True
    role = admin_role_for_user(telegram_id)
    if role:
        await message.answer(f"Недостаточно прав. Ваша роль: {role}, требуется: {permission}.")
    else:
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
        required_permission = ADMIN_ACTION_PERMISSIONS.get(pending.action, "owner")
        if not has_admin_permission(admin_id, required_permission):
            pending.status = "DENIED"
            pending.executed_at = datetime.now(UTC)
            pending.result = {"error": "insufficient_permissions", "required_permission": required_permission}
            session.add(AuditLog(actor=f"admin:{admin_id}", action=f"admin_{pending.action}_denied", entity="admin_action", entity_id=str(pending.id), details={"target": pending.target, "required_permission": required_permission}))
            await session.commit()
            return f"Недостаточно прав: требуется {required_permission}."
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
                await notify_admin(
                    settings,
                    "ALANET: admin grant executed.\n"
                    f"Client: {telegram_id}\n"
                    f"Plan: {plan.name}\n"
                    f"Expires at: {subscription.expires_at.astimezone().strftime('%d.%m.%Y %H:%M')}\n"
                    f"Action ID: {pending.id}",
                )
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
                await notify_admin(
                    settings,
                    "ALANET: admin extend executed.\n"
                    f"Client: {telegram_id}\n"
                    f"Days: {days}\n"
                    f"Expires at: {expiry.astimezone().strftime('%d.%m.%Y %H:%M')}\n"
                    f"Action ID: {pending.id}",
                )
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
    if admin_role_for_user(callback.from_user.id) is None:
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
        async with SessionLocal() as session:
            pending = await session.get(AdminAction, action_id)
        required_permission = ADMIN_ACTION_PERMISSIONS.get(pending.action if pending else "", "owner")
        if not has_admin_permission(callback.from_user.id, required_permission):
            await callback.answer(f"Недостаточно прав: требуется {required_permission}", show_alert=True)
            return
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
    role = admin_role_for_user(message.from_user.id if message.from_user else None) or "unknown"
    await message.answer(
        f"Административное меню ALANET\nВаша роль: {role}\n\n"
        "/status — короткий светофор проекта\n"
        "/incident — карточка incident mode одним экраном\n"
        "/health — полная диагностика\n"
        "/ports — проверка host-портов Remnawave\n"
        "/backup — статус последнего бэкапа\n"
        "/disk — место на prod и безопасная очистка\n"
        "/cleanup — статус автоочистки prod\n"
        "/deploy_status — версия backend/web и последний deploy\n"
        "/node_backup — статус backup всех нод\n"
        "/failed — всё, что требует внимания\n"
        "/risk — короткая карта рисков\n"
        "/audit [дни] — журнал админских и системных действий\n"
        "/stats — статистика клиентов и заказов\n"
        "/user <telegram_id|@username|email> — карточка клиента\n"
        "/grant <telegram_id> <trial|start|calm|year> — выдать тариф\n"
        "/extend <telegram_id> <дни> — продлить подписку\n"
        "/revoke <telegram_id> — отозвать подписку\n"
        "/nodes — состояние нод Remnawave\n"
        "/node <name> — карточка ноды\n"
        "/remnawave_sync — сверка registry с Remnawave\n"
        "/orders [STATUS|all] [дни] — список заказов\n"
        "/payments [дни] — последние оплаты\n"
        "/finance [дни] — финансовая сверка YooKassa\n"
        "/retry <order_id> — повторить один failed provisioning\n"
        "/retry_failed [limit] — повторить все failed provisioning"
    )


async def send_admin_lines(message: Message, lines: list[str]) -> None:
    text = "\n".join(lines)
    if len(text) <= 3900:
        await message.answer(text)
        return
    chunk: list[str] = []
    size = 0
    for line in lines:
        if size + len(line) + 1 > 3900 and chunk:
            await message.answer("\n".join(chunk))
            chunk = []
            size = 0
        chunk.append(line)
        size += len(line) + 1
    if chunk:
        await message.answer("\n".join(chunk))


def ok_bad(value: bool) -> str:
    return "✅" if value else "❌"


def warn_bad(value: bool) -> str:
    return "✅" if value else "⚠️"


def short_id(value: uuid.UUID | str | None) -> str:
    return "—" if value is None else str(value)[:8]


async def tcp_port_open(host: str, port: int, timeout: float = 5.0) -> tuple[bool, str | None]:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True, None
    except Exception as exc:
        return False, type(exc).__name__


async def fetch_status(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.get(url)
        return str(response.status_code)
    except Exception as exc:
        return f"ERR:{type(exc).__name__}"


def host_node_ids(host: dict) -> set[str]:
    raw_nodes = host.get("nodes") or []
    if not isinstance(raw_nodes, list):
        return set()
    result: set[str] = set()
    for item in raw_nodes:
        if isinstance(item, str):
            result.add(item)
        elif isinstance(item, dict):
            value = item.get("uuid") or item.get("id")
            if value is not None:
                result.add(str(value))
    return result


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
    if not await require_admin(message, "provision"):
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
    if not await require_admin(message, "provision"):
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
    if not await require_admin(message, "revoke"):
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
    if not await require_admin(message, "provision"):
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


@router.message(Command("health"))
async def admin_health(message: Message) -> None:
    if not await require_admin(message):
        return
    lines = ["Диагностика ALANET"]
    async with SessionLocal() as session:
        try:
            customers = await session.scalar(select(func.count()).select_from(Customer))
            active = await session.scalar(select(func.count()).select_from(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE))
            failed = await session.scalar(select(func.count()).select_from(Order).where(Order.status == OrderStatus.PROVISIONING_FAILED))
            succeeded_payments = await session.scalar(select(func.count()).select_from(Payment).where(Payment.status == "succeeded"))
            lines.append(f"{ok_bad(True)} DB: ok")
            lines.append(f"Клиентов: {customers}, активных подписок: {active}, failed provisioning: {failed}, успешных оплат: {succeeded_payments}")
        except Exception as exc:
            log.exception("admin_health_db_failed")
            lines.append(f"{ok_bad(False)} DB: {type(exc).__name__}")
    for name, url, expected in [
        ("site", "https://alanet.ru/", "200"),
        ("account", "https://account.alanet.ru/", "200"),
        ("api", "https://api.alanet.ru/health", "200"),
        ("panel", "https://panel.alanet.ru/", "200"),
        ("subscription root", "https://sub.alanet.ru/", "404"),
    ]:
        status = await fetch_status(url)
        lines.append(f"{ok_bad(status == expected)} {name}: {status}")
    try:
        client = RemnawaveClient(settings)
        nodes = await client.list_nodes()
        hosts = await client.list_hosts()
        connected = sum(1 for node in nodes if node.get("isConnected"))
        enabled_hosts = [host for host in hosts if not host.get("isDisabled", False)]
        lines.append(f"{ok_bad(connected == len(nodes) and len(nodes) > 0)} Remnawave nodes: {connected}/{len(nodes)} connected")
        lines.append(f"{ok_bad(len(enabled_hosts) > 0)} Remnawave hosts: {len(enabled_hosts)} active")
    except Exception as exc:
        log.exception("admin_health_remnawave_failed")
        lines.append(f"{ok_bad(False)} Remnawave: {type(exc).__name__}")
    lines.extend(prod_ops_status_lines())
    lines.extend(backup_status_lines())
    await send_admin_lines(message, lines)


@router.message(Command("ports"))
async def admin_ports(message: Message) -> None:
    if not await require_admin(message):
        return
    try:
        hosts = await RemnawaveClient(settings).list_hosts()
    except Exception:
        log.exception("admin_ports_hosts_failed")
        await message.answer("Не удалось получить hosts из Remnawave.")
        return
    enabled_hosts = [host for host in hosts if not host.get("isDisabled", False)]
    if not enabled_hosts:
        await message.answer("Активные hosts в Remnawave не найдены.")
        return
    checks = []
    for host in enabled_hosts:
        address = str(host.get("address") or "")
        try:
            port = int(host.get("port"))
        except (TypeError, ValueError):
            checks.append((host, False, "bad_port"))
            continue
        checks.append((host, *await tcp_port_open(address, port)))
    lines = ["Проверка host-портов Remnawave:"]
    ok_count = 0
    for host, ok, error in checks:
        if ok:
            ok_count += 1
        remark = host.get("remark") or host.get("name") or "host"
        address = host.get("address") or "?"
        port = host.get("port") or "?"
        suffix = "" if ok else f" ({error})"
        lines.append(f"{ok_bad(ok)} {remark}: {address}:{port}{suffix}")
    lines.insert(1, f"Итог: {ok_count}/{len(checks)} доступны")
    await send_admin_lines(message, lines)


MONITOR_DIR = Path("/var/lib/alanet-monitor")


def _format_status_age(timestamp: str | None) -> tuple[bool, str]:
    if not timestamp:
        return False, "нет timestamp"
    try:
        created_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
    except ValueError:
        return False, "timestamp не читается"
    age_hours = (datetime.now(UTC) - created_at.astimezone(UTC)).total_seconds() / 3600
    return age_hours <= 36, f"{age_hours:.1f} ч"


def _read_monitor_status(name: str) -> dict | None:
    status_path = MONITOR_DIR / name
    try:
        return json.loads(status_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        log.exception("monitor_status_read_failed", path=str(status_path))
        return {"status": "failed", "message": "status json не читается", "path": str(status_path)}


def _format_rate_bps(value: int | float | None) -> str:
    if value is None:
        return "warming up"
    try:
        bps = float(value)
    except (TypeError, ValueError):
        return "?"
    mbps = bps * 8 / 1024 / 1024
    if mbps >= 1:
        return f"{mbps:.1f} Mbps"
    return f"{bps / 1024:.1f} KB/s"


def _format_rate_bytes(value: int | float | None) -> str:
    if value is None:
        return "warming up"
    try:
        bps = float(value)
    except (TypeError, ValueError):
        return "?"
    mb = bps / 1024 / 1024
    if mb >= 1:
        return f"{mb:.1f} MB/s"
    return f"{bps / 1024:.1f} KB/s"


def prod_ops_status_lines() -> list[str]:
    status = _read_monitor_status("prod-ops.status.json")
    if not status:
        return [
            f"{ok_bad(False)} Prod ops collector: status not found",
            "Expected: /var/lib/alanet-monitor/prod-ops.status.json",
        ]

    fresh, age = _format_status_age(status.get("timestamp"))
    status_name = str(status.get("status") or "unknown")
    ok = status_name == "ok" and fresh
    badge = "OK" if status_name == "ok" else "WARN" if status_name == "warning" else "INCIDENT"
    load = status.get("load") or {}
    memory = status.get("memory") or {}
    network_rates = status.get("network_rates") or {}
    disk_rates = status.get("disk_rates") or {}
    containers = status.get("containers") or {}
    problems = status.get("problems") or []

    lines = [
        f"{ok_bad(ok)} Prod ops: {badge}, age {age}{'' if fresh else ' (stale)'}",
        f"Load: {load.get('one', '?')} / {load.get('five', '?')} / {load.get('fifteen', '?')}",
        f"RAM: {memory.get('used_percent', '?')}%",
        f"Network: rx {_format_rate_bps(network_rates.get('rx_bps'))}, tx {_format_rate_bps(network_rates.get('tx_bps'))}",
        f"Disk IO: read {_format_rate_bytes(disk_rates.get('read_bps'))}, write {_format_rate_bytes(disk_rates.get('write_bps'))}",
        f"Containers: {containers.get('running_count', '?')} running",
        f"Health freshness: {status.get('health_summary_age_seconds', '?')}s",
    ]
    for item in problems[:5]:
        lines.append(f"- {item.get('severity', 'warning')}: {item.get('message', '')}")
    return lines


def backup_status_lines() -> list[str]:
    lines: list[str] = []
    backup_status = _read_monitor_status("backup.status.json")
    if backup_status:
        fresh, age = _format_status_age(backup_status.get("timestamp"))
        ok = backup_status.get("status") == "ok" and fresh
        message = backup_status.get("message") or ""
        external = backup_status.get("external_result") or backup_status.get("external")
        if not external and "external=" in message:
            external = message.rsplit("external=", 1)[-1].split()[0].strip(" ;,.")
        external = external or ("uploaded" if backup_status.get("external_archive") else "unknown")
        archive = Path(str(backup_status.get("archive") or "")).name or "unknown"
        lines.append(f"{ok_bad(ok)} Backup: {archive}, age {age}, external={external}")
        if message:
            lines.append(f"Backup detail: {message}")
    else:
        candidates: list[Path] = []
        for pattern in ["/var/backups/alanet/alanet-*.tar.gz.enc", "/var/backups/alanet/alanet-*.tar.gz", "/opt/alanet/backups/*.tar.gz"]:
            candidates.extend(Path("/").glob(pattern.lstrip("/")))
        if not candidates:
            lines.append(f"{ok_bad(False)} Backup: архивы не найдены или недоступны в контейнере")
        else:
            latest = max(candidates, key=lambda item: item.stat().st_mtime)
            age = datetime.now().timestamp() - latest.stat().st_mtime
            age_hours = age / 3600
            size_mb = latest.stat().st_size / 1024 / 1024
            fresh = age_hours <= 36
            lines.append(f"{ok_bad(fresh)} Backup: {latest.name}, {size_mb:.1f} MB, возраст {age_hours:.1f} ч")

    restore_status = _read_monitor_status("restore-test.status.json")
    if restore_status:
        fresh, age = _format_status_age(restore_status.get("timestamp"))
        ok = restore_status.get("status") == "ok" and fresh
        archive = restore_status.get("archive") or "unknown"
        source = restore_status.get("source") or "unknown"
        counts = (
            f"tables={restore_status.get('tables')}, customers={restore_status.get('customers')}, "
            f"orders={restore_status.get('orders')}, subscriptions={restore_status.get('subscriptions')}, "
            f"payments={restore_status.get('payments')}"
        )
        lines.append(f"{ok_bad(ok)} Restore-test: {archive}, source={source}, age {age}")
        lines.append(f"Restore detail: {counts}")
    else:
        lines.append(f"{ok_bad(False)} Restore-test: статус не найден")
    return lines


def _status_badge(status_name: str | None) -> str:
    normalized = (status_name or "unknown").lower()
    if normalized in {"ok", "up", "active", "success"}:
        return "✅"
    if normalized in {"warning", "partial", "degraded"}:
        return "⚠️"
    return "❌"


async def project_status_lines() -> list[str]:
    lines = ["ALANET status"]
    problems: list[str] = []

    async with SessionLocal() as session:
        try:
            customers = await session.scalar(select(func.count()).select_from(Customer))
            active_subs = await session.scalar(select(func.count()).select_from(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE))
            failed_provisioning = await session.scalar(select(func.count()).select_from(Order).where(Order.status == OrderStatus.PROVISIONING_FAILED))
            lines.append(f"✅ DB: ok · клиентов {customers} · активных подписок {active_subs}")
            if failed_provisioning:
                problems.append(f"failed provisioning: {failed_provisioning}")
        except Exception as exc:
            log.exception("admin_status_db_failed")
            lines.append(f"❌ DB: {type(exc).__name__}")
            problems.append("DB unavailable")

    http_checks = [
        ("site", "https://alanet.ru/", "200"),
        ("account", "https://account.alanet.ru/", "200"),
        ("api", "https://api.alanet.ru/health", "200"),
        ("panel", "https://panel.alanet.ru/", "200"),
    ]
    http_ok = 0
    for name, url, expected in http_checks:
        status = await fetch_status(url)
        if status == expected:
            http_ok += 1
        else:
            problems.append(f"{name} HTTP {status}")
    lines.append(f"{ok_bad(http_ok == len(http_checks))} HTTP: {http_ok}/{len(http_checks)}")

    try:
        client = RemnawaveClient(settings)
        nodes = await client.list_nodes()
        hosts = await client.list_hosts()
        connected = sum(1 for node in nodes if node.get("isConnected"))
        enabled_hosts = [host for host in hosts if not host.get("isDisabled", False)]
        rem_ok = connected == len(nodes) and connected > 0 and len(enabled_hosts) > 0
        lines.append(f"{ok_bad(rem_ok)} Remnawave: nodes {connected}/{len(nodes)}, hosts {len(enabled_hosts)}")
        if not rem_ok:
            problems.append("Remnawave nodes/hosts degraded")
    except Exception as exc:
        log.exception("admin_status_remnawave_failed")
        lines.append(f"❌ Remnawave: {type(exc).__name__}")
        problems.append("Remnawave unavailable")

    health_status = _read_monitor_status("health.status.json")
    if health_status:
        fresh, age = _format_status_age(health_status.get("timestamp"))
        health_state = str(health_status.get("status") or "unknown")
        warning_count = health_status.get("warning_count", 0)
        problem_count = health_status.get("problem_count", 0)
        lines.append(
            f"{_status_badge(health_state) if fresh else '⚠️'} Health-check: {health_state}, "
            f"warnings {warning_count}, problems {problem_count}, age {age}"
        )
        for item in (health_status.get("problems") or [])[:3]:
            problems.append(str(item))
        if not fresh:
            problems.append("health status stale")
        elif health_state not in {"ok", "warning"}:
            problems.append(f"health-check {health_state}")
    else:
        health_state = "unknown"
        try:
            health_state = (MONITOR_DIR / "health.state").read_text(encoding="utf-8").strip()
        except Exception:
            problems.append("health state missing")
        lines.append(f"{_status_badge(health_state)} Health-check: {health_state}")

    prod_ops = _read_monitor_status("prod-ops.status.json")
    if prod_ops:
        fresh, age = _format_status_age(prod_ops.get("timestamp"))
        prod_status = str(prod_ops.get("status") or "unknown")
        load = prod_ops.get("load") or {}
        memory = prod_ops.get("memory") or {}
        lines.append(
            f"{_status_badge(prod_status) if fresh else '⚠️'} Prod ops: {prod_status}, "
            f"load {load.get('one', '?')}, RAM {memory.get('used_percent', '?')}%, age {age}"
        )
        if prod_status not in {"ok", "warning"} or not fresh:
            problems.append("prod ops degraded")
    else:
        lines.append("⚠️ Prod ops: no status")
        problems.append("prod ops missing")

    backup_status = _read_monitor_status("backup.status.json")
    if backup_status:
        fresh, age = _format_status_age(backup_status.get("timestamp"))
        status_name = str(backup_status.get("status") or "unknown")
        external = backup_status.get("external_result") or backup_status.get("external") or ("uploaded" if backup_status.get("external_archive") else "unknown")
        lines.append(f"{_status_badge(status_name) if fresh else '⚠️'} Backup: {status_name}, external={external}, age {age}")
        if status_name != "ok" or not fresh or external not in {"uploaded", "copied"}:
            problems.append("backup requires attention")
    else:
        lines.append("⚠️ Backup: no status")
        problems.append("backup status missing")

    restore_status = _read_monitor_status("restore-test.status.json")
    if restore_status:
        fresh, age = _format_status_age(restore_status.get("timestamp"))
        status_name = str(restore_status.get("status") or "unknown")
        lines.append(f"{_status_badge(status_name) if fresh else '⚠️'} Restore-test: {status_name}, age {age}")
    else:
        lines.append("⚠️ Restore-test: no status")

    e2e_status = _read_monitor_status("e2e.status.json")
    if e2e_status:
        fresh, age = _format_status_age(e2e_status.get("timestamp"))
        status_name = str(e2e_status.get("status") or "unknown")
        lines.append(f"{_status_badge(status_name) if fresh else '⚠️'} E2E: {status_name}, {e2e_status.get('ok_count', '?')}/{e2e_status.get('total_count', '?')}, age {age}")
        if status_name != "ok" or not fresh:
            problems.append("E2E synthetic check requires attention")
    else:
        lines.append("⚠️ E2E: no status")

    if problems:
        lines.append("Проблемы:")
        lines.extend(f"- {item}" for item in problems[:8])
    else:
        lines.append("Итог: ✅ коммерческий контур в норме")
    return lines


async def incident_card_lines() -> list[str]:
    lines = ["🚦 ALANET incident card"]
    problems: list[str] = []

    health_status = _read_monitor_status("health.status.json")
    if health_status:
        fresh, age = _format_status_age(health_status.get("timestamp"))
        health_state = str(health_status.get("status") or "unknown")
        warnings = health_status.get("warnings") or []
        health_problems = health_status.get("problems") or []
        lines.append(
            f"{_status_badge(health_state) if fresh else '⚠️'} Overall: {health_state}, "
            f"warn {len(warnings)}, problem {len(health_problems)}, age {age}"
        )
        if not fresh:
            problems.append("health snapshot stale")
        problems.extend(str(item) for item in health_problems[:4])
        if not health_problems:
            problems.extend(str(item) for item in warnings[:2])
    else:
        lines.append("❌ Overall: no health.status.json")
        problems.append("health.status.json missing")

    async with SessionLocal() as session:
        try:
            customers = await session.scalar(select(func.count()).select_from(Customer)) or 0
            active_subs = await session.scalar(select(func.count()).select_from(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE)) or 0
            failed_provisioning = await session.scalar(select(func.count()).select_from(Order).where(Order.status == OrderStatus.PROVISIONING_FAILED)) or 0
            pending_orders = await session.scalar(select(func.count()).select_from(Order).where(Order.status == OrderStatus.PROVISIONING)) or 0
            lines.append(f"✅ DB: ok · clients {customers} · active {active_subs} · failed/pending {failed_provisioning}/{pending_orders}")
            if failed_provisioning:
                problems.append(f"failed provisioning: {failed_provisioning}")
        except Exception as exc:
            log.exception("admin_incident_db_failed")
            lines.append(f"❌ DB: {type(exc).__name__}")
            problems.append("DB unavailable")

    http_checks = [
        ("site", "https://alanet.ru/", "200"),
        ("account", "https://account.alanet.ru/", "200"),
        ("api", "https://api.alanet.ru/health", "200"),
        ("panel", "https://panel.alanet.ru/", "200"),
    ]
    http_results = await asyncio.gather(*(fetch_status(url) for _name, url, _expected in http_checks), return_exceptions=True)
    http_ok = 0
    http_bad: list[str] = []
    for (name, _url, expected), result in zip(http_checks, http_results, strict=False):
        status = type(result).__name__ if isinstance(result, Exception) else str(result)
        if status == expected:
            http_ok += 1
        else:
            http_bad.append(f"{name}:{status}")
    lines.append(f"{ok_bad(http_ok == len(http_checks))} Web/API: {http_ok}/{len(http_checks)}" + (f" · {', '.join(http_bad[:3])}" if http_bad else ""))
    problems.extend(f"HTTP {item}" for item in http_bad[:3])

    try:
        client = RemnawaveClient(settings)
        nodes, hosts = await asyncio.gather(client.list_nodes(), client.list_hosts())
        connected = sum(1 for node in nodes if node.get("isConnected"))
        enabled_hosts = [host for host in hosts if not host.get("isDisabled", False)]
        port_tasks = []
        host_checks = []
        for host in enabled_hosts:
            address = str(host.get("address") or "")
            try:
                port = int(host.get("port"))
            except (TypeError, ValueError):
                host_checks.append((host, False, "bad_port"))
                continue
            port_tasks.append((host, tcp_port_open(address, port, timeout=3.0)))
        port_results = await asyncio.gather(*(task for _host, task in port_tasks), return_exceptions=True)
        for (host, _task), result in zip(port_tasks, port_results, strict=False):
            if isinstance(result, Exception):
                host_checks.append((host, False, type(result).__name__))
            else:
                ok, error = result
                host_checks.append((host, ok, error))
        host_ok = sum(1 for _host, ok, _error in host_checks if ok)
        bad_hosts = [
            f"{host.get('remark') or host.get('name') or host.get('address')}:{host.get('port')} {error}"
            for host, ok, error in host_checks
            if not ok
        ]
        rem_ok = connected == len(nodes) and connected > 0 and host_ok == len(host_checks)
        lines.append(f"{ok_bad(rem_ok)} Remnawave: nodes {connected}/{len(nodes)} · ports {host_ok}/{len(host_checks)}")
        problems.extend(f"host port {item}" for item in bad_hosts[:4])
        if connected != len(nodes):
            disconnected = [str(node.get("name") or node.get("address")) for node in nodes if not node.get("isConnected")]
            problems.extend(f"node disconnected: {item}" for item in disconnected[:4])
    except Exception as exc:
        log.exception("admin_incident_remnawave_failed")
        lines.append(f"❌ Remnawave/ports: {type(exc).__name__}")
        problems.append("Remnawave/ports unavailable")

    prod_ops = _read_monitor_status("prod-ops.status.json")
    disk = _read_monitor_status("disk.status.json")
    if prod_ops:
        fresh, age = _format_status_age(prod_ops.get("timestamp"))
        prod_status = str(prod_ops.get("status") or "unknown")
        load = prod_ops.get("load") or {}
        memory = prod_ops.get("memory") or {}
        containers = prod_ops.get("containers") or {}
        lines.append(
            f"{_status_badge(prod_status) if fresh else '⚠️'} Prod: {prod_status} · "
            f"load {load.get('one', '?')} · RAM {memory.get('used_percent', '?')}% · "
            f"containers {containers.get('running_count', '?')} · age {age}"
        )
        if not fresh or prod_status not in {"ok", "warning"}:
            problems.append("prod ops degraded")
    else:
        lines.append("⚠️ Prod: no prod-ops status")
        problems.append("prod-ops status missing")

    if disk:
        fresh, age = _format_status_age(disk.get("timestamp"))
        disk_status = str(disk.get("status") or "unknown")
        root = disk.get("root") or {}
        lines.append(
            f"{_status_badge(disk_status) if fresh else '⚠️'} Disk: {disk_status} · "
            f"/ {root.get('used_percent', '?')}% · free {_format_bytes(root.get('free_bytes'))} · age {age}"
        )
        if not fresh or disk_status not in {"ok", "warning"}:
            problems.append("disk requires attention")
    else:
        lines.append("⚠️ Disk: no status")
        problems.append("disk status missing")

    backup = _read_monitor_status("backup.status.json")
    restore = _read_monitor_status("restore-test.status.json")
    node_backup = _read_monitor_status("node-backup.status.json")
    backup_parts: list[str] = []
    backup_ok = True
    for label, status in [("backup", backup), ("restore", restore), ("nodes", node_backup)]:
        if not status:
            backup_parts.append(f"{label}:missing")
            problems.append(f"{label} status missing")
            backup_ok = False
            continue
        fresh, age = _format_status_age(status.get("timestamp"))
        status_name = str(status.get("status") or "unknown")
        backup_parts.append(f"{label}:{status_name}/{age}")
        if not fresh or status_name not in {"ok", "warning"}:
            problems.append(f"{label} {status_name}")
            backup_ok = False
    lines.append(f"{ok_bad(backup_ok)} Backup: " + " · ".join(backup_parts))

    e2e = _read_monitor_status("e2e.status.json")
    if e2e:
        fresh, age = _format_status_age(e2e.get("timestamp"))
        e2e_status = str(e2e.get("status") or "unknown")
        lines.append(f"{_status_badge(e2e_status) if fresh else '⚠️'} E2E: {e2e_status} · {e2e.get('ok_count', '?')}/{e2e.get('total_count', '?')} · age {age}")
        if not fresh or e2e_status not in {"ok", "warning"}:
            problems.append("E2E synthetic check requires attention")
    else:
        lines.append("⚠️ E2E: no status")

    unique_problems = list(dict.fromkeys(item for item in problems if item))
    if unique_problems:
        lines.append("Attention:")
        lines.extend(f"- {item}" for item in unique_problems[:8])
    else:
        lines.append("Итог: ✅ incident не обнаружен")
    lines.append("Детали: /health /ports /backup /disk")
    return lines


@router.message(Command("status"))
async def admin_status(message: Message) -> None:
    if not await require_admin(message):
        return
    await send_admin_lines(message, await project_status_lines())


@router.message(Command("incident"))
async def admin_incident(message: Message) -> None:
    if not await require_admin(message):
        return
    await send_admin_lines(message, await incident_card_lines())


def latest_backup_status_line() -> str:
    return "\n".join(backup_status_lines())


def latest_backup_archive_line() -> str:
    candidates: list[Path] = []
    for pattern in ["/var/backups/alanet/alanet-*.tar.gz", "/opt/alanet/backups/*.tar.gz"]:
        candidates.extend(Path("/").glob(pattern.lstrip("/")))
    if not candidates:
        return f"{ok_bad(False)} Backup: архивы не найдены или недоступны в контейнере"
    latest = max(candidates, key=lambda item: item.stat().st_mtime)
    age = datetime.now().timestamp() - latest.stat().st_mtime
    age_hours = age / 3600
    size_mb = latest.stat().st_size / 1024 / 1024
    fresh = age_hours <= 36
    return f"{ok_bad(fresh)} Backup: {latest.name}, {size_mb:.1f} MB, возраст {age_hours:.1f} ч"


@router.message(Command("backup"))
async def admin_backup(message: Message) -> None:
    if not await require_admin(message):
        return
    await message.answer(latest_backup_status_line())


def _format_bytes(value: int | float | None) -> str:
    if value is None:
        return "?"
    try:
        size = float(value)
    except (TypeError, ValueError):
        return "?"
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if abs(size) < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size:.0f} B"
        size /= 1024
    return f"{size:.1f} TB"


def disk_status_lines() -> list[str]:
    status = _read_monitor_status("disk.status.json")
    if not status:
        return [
            "Disk prod: статус не найден.",
            "Collector должен писать /var/lib/alanet-monitor/disk.status.json.",
            "Ручная проверка на prod: df -h / && docker system df",
        ]

    fresh, age = _format_status_age(status.get("timestamp"))
    root = status.get("root") or {}
    used_percent = root.get("used_percent")
    status_name = status.get("status") or "unknown"
    badge = "OK" if status_name == "ok" else "WARN" if status_name == "warning" else "INCIDENT"

    lines = [
        f"Disk prod: {badge}",
        f"Age: {age}{'' if fresh else ' (stale)'}",
        f"/: {used_percent if used_percent is not None else '?'}% used, free {_format_bytes(root.get('free_bytes'))} of {_format_bytes(root.get('total_bytes'))}",
    ]

    top_dirs = status.get("top_dirs") or {}
    for path in ["/var", "/opt", "/var/lib/containerd"]:
        entries = top_dirs.get(path) or []
        lines.append(f"Top {path}:")
        if not entries:
            lines.append("- no data")
            continue
        for item in entries[:6]:
            lines.append(f"- {_format_bytes(item.get('bytes'))} {item.get('path')}")

    docker = status.get("docker") or {}
    lines.append("Docker:")
    if docker:
        for key in ["images", "containers", "volumes", "build_cache"]:
            item = docker.get(key) or {}
            size = item.get("size") or item.get("total") or "?"
            reclaimable = item.get("reclaimable") or "?"
            lines.append(f"- {key}: {size}, reclaimable {reclaimable}")
    else:
        lines.append("- no data")

    lines.append("Safe cleanup:")
    safe_cleanup = status.get("safe_cleanup") or []
    if safe_cleanup:
        lines.extend(f"- {item}" for item in safe_cleanup)
    else:
        lines.append("- nothing obvious")
    return lines


@router.message(Command("disk"))
async def admin_disk(message: Message) -> None:
    if not await require_admin(message):
        return
    await send_admin_lines(message, disk_status_lines())


def cleanup_status_lines() -> list[str]:
    status = _read_monitor_status("cleanup.status.json")
    if not status:
        return [
            "Cleanup prod: статус не найден.",
            "Ожидается файл /var/lib/alanet-monitor/cleanup.status.json.",
            "Host-команда: sudo systemctl start alanet-safe-cleanup.service",
        ]
    fresh, age = _format_status_age(status.get("timestamp"))
    status_name = str(status.get("status") or "unknown")
    lines = [
        f"{_status_badge(status_name) if fresh else '⚠️'} Cleanup prod: {status_name}, age {age}",
        f"Trigger: / >= {status.get('trigger_percent', '?')}%",
        f"Disk: {status.get('disk_before_percent', '?')}% → {status.get('disk_after_percent', '?')}%",
    ]
    actions = status.get("actions") or []
    if actions:
        lines.append("Actions:")
        lines.extend(f"- {item}" for item in actions[:8])
    errors = status.get("errors") or []
    if errors:
        lines.append("Errors:")
        lines.extend(f"- {item}" for item in errors[:5])
    lines.append("Note: Telegram bot intentionally has read-only access to host cleanup status.")
    return lines


@router.message(Command("cleanup"))
async def admin_cleanup(message: Message) -> None:
    if not await require_admin(message, "ops"):
        return
    await send_admin_lines(message, cleanup_status_lines())


def deploy_status_lines() -> list[str]:
    status = _read_monitor_status("deploy.status.json")
    lines = ["Deploy status"]
    if status:
        fresh, age = _format_status_age(status.get("timestamp"))
        status_name = str(status.get("status") or "unknown")
        lines.extend([
            f"{_status_badge(status_name) if fresh else '⚠️'} Last deploy: {status_name}, age {age}",
            f"Mode: {status.get('mode', 'unknown')}",
            f"Backend image: {status.get('backend_image') or 'unknown'}",
            f"Backup dir: {status.get('backup_dir') or 'unknown'}",
        ])
    else:
        lines.extend([
            "⚠️ Last deploy status: no status file",
            "Expected: /var/lib/alanet-monitor/deploy.status.json",
        ])
    lines.extend(prod_ops_status_lines()[:4])
    return lines


@router.message(Command("deploy_status"))
async def admin_deploy_status(message: Message) -> None:
    if not await require_admin(message):
        return
    await send_admin_lines(message, deploy_status_lines())


def node_backup_status_lines() -> list[str]:
    status = _read_monitor_status("node-backup.status.json")
    if not status:
        return [
            "Node backup: статус не найден.",
            "Ожидается файл /var/lib/alanet-monitor/node-backup.status.json.",
        ]
    fresh, age = _format_status_age(status.get("timestamp"))
    status_name = str(status.get("status") or "unknown")
    failed_nodes = status.get("failed_nodes") or []
    ignored_nodes = status.get("ignored_nodes") or []
    lines = [
        f"{_status_badge(status_name) if fresh else '⚠️'} Node backup: {status_name}, age {age}",
        f"OK: {status.get('ok_count', '?')}, failed: {status.get('fail_count', '?')}, ignored: {status.get('ignored_count', len(ignored_nodes))}",
        f"S3: {status.get('s3_target') or 'unknown'}",
        f"Archive: {status.get('encrypted_archive') or status.get('archive') or 'unknown'}",
    ]
    if ignored_nodes:
        lines.append("Ignored / controlled risk:")
        lines.extend(f"- {item}" for item in ignored_nodes[:12])
        lines.append("Policy: эти shared-ноды не трогаем без отдельной команды.")
    if failed_nodes:
        lines.append("Failed nodes:")
        lines.extend(f"- {item}" for item in failed_nodes[:12])
        lines.append("Next: проверить SSH deploy key на этих нодах и повторить backup.")
    return lines


@router.message(Command("node_backup"))
async def admin_node_backup(message: Message) -> None:
    if not await require_admin(message):
        return
    await send_admin_lines(message, node_backup_status_lines())


async def failed_status_lines() -> list[str]:
    lines = ["ALANET failed / attention"]
    async with SessionLocal() as session:
        failed_provisioning = await session.scalar(select(func.count()).select_from(Order).where(Order.status == OrderStatus.PROVISIONING_FAILED)) or 0
        pending_orders = await session.scalar(select(func.count()).select_from(Order).where(Order.status == OrderStatus.PROVISIONING)) or 0
        failed_actions = await session.scalar(select(func.count()).select_from(AdminAction).where(AdminAction.status == "FAILED")) or 0
        lines.append(f"Provisioning failed: {failed_provisioning}")
        lines.append(f"Provisioning pending: {pending_orders}")
        lines.append(f"Admin actions failed: {failed_actions}")
    health_state = "unknown"
    try:
        health_state = (MONITOR_DIR / "health.state").read_text(encoding="utf-8").strip()
    except Exception:
        pass
    lines.append(f"Health state: {health_state}")
    for name, label in [
        ("backup.status.json", "Backup"),
        ("node-backup.status.json", "Node backup"),
        ("cleanup.status.json", "Cleanup"),
        ("e2e.status.json", "E2E"),
        ("restore-test.status.json", "Restore-test"),
    ]:
        status = _read_monitor_status(name)
        if not status:
            lines.append(f"⚠️ {label}: no status")
            continue
        fresh, age = _format_status_age(status.get("timestamp"))
        status_name = str(status.get("status") or "unknown")
        if status_name != "ok" or not fresh:
            lines.append(f"{_status_badge(status_name)} {label}: {status_name}, age {age}")
        if name == "node-backup.status.json" and status.get("ignored_count"):
            lines.append(f"ℹ️ Node backup controlled risk: ignored {status.get('ignored_count')} shared nodes")
    return lines


@router.message(Command("failed"))
async def admin_failed(message: Message) -> None:
    if not await require_admin(message):
        return
    await send_admin_lines(message, await failed_status_lines())


async def risk_status_lines() -> list[str]:
    lines = ["ALANET risk map"]
    disk = _read_monitor_status("disk.status.json")
    if disk:
        root = disk.get("root") or {}
        thresholds = disk.get("thresholds") or {}
        used = root.get("used_percent")
        incident = thresholds.get("incident_percent")
        lines.append(f"{'⚠️' if used and used >= 85 else '✅'} Prod disk: {used}% used, incident {incident}%")
    node_backup = _read_monitor_status("node-backup.status.json")
    if node_backup:
        fail_count = int(node_backup.get("fail_count") or 0)
        ignored_count = int(node_backup.get("ignored_count") or 0)
        lines.append(f"{'⚠️' if fail_count else '✅'} Node backup: failed {fail_count}, ignored controlled {ignored_count}")
    cleanup = _read_monitor_status("cleanup.status.json")
    if cleanup:
        lines.append(f"{_status_badge(str(cleanup.get('status') or 'unknown'))} Cleanup: {cleanup.get('status')}, disk {cleanup.get('disk_after_percent', '?')}%")
    e2e = _read_monitor_status("e2e.status.json")
    if e2e:
        lines.append(f"{_status_badge(str(e2e.get('status') or 'unknown'))} E2E: {e2e.get('status')}, checks {e2e.get('ok_count', '?')}/{e2e.get('total_count', '?')}")
    async with SessionLocal() as session:
        failed_provisioning = await session.scalar(select(func.count()).select_from(Order).where(Order.status == OrderStatus.PROVISIONING_FAILED)) or 0
        expiring = await session.scalar(
            select(func.count()).select_from(Subscription).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at <= datetime.now(UTC) + timedelta(days=1),
            )
        ) or 0
    lines.append(f"{'⚠️' if failed_provisioning else '✅'} Failed provisioning: {failed_provisioning}")
    lines.append(f"{'⚠️' if expiring else '✅'} Expiring in 24h: {expiring}")
    lines.append("Top next actions: node backup → off-host Docker build → staging payments.")
    return lines


@router.message(Command("risk"))
async def admin_risk(message: Message) -> None:
    if not await require_admin(message):
        return
    await send_admin_lines(message, await risk_status_lines())


@router.message(Command("audit"))
async def admin_audit(message: Message) -> None:
    if not await require_admin(message, "audit"):
        return
    args = command_args(message)
    try:
        days = int(args[0]) if args else 7
    except ValueError:
        await message.answer("Использование: /audit [дни]")
        return
    if days < 1 or days > 90:
        await message.answer("Период должен быть от 1 до 90 дней.")
        return
    since = datetime.now(UTC) - timedelta(days=days)
    query = (
        select(AuditLog)
        .where(AuditLog.timestamp >= since)
        .order_by(AuditLog.timestamp.desc())
        .limit(30)
    )
    async with SessionLocal() as session:
        rows = list((await session.scalars(query)).all())
    if not rows:
        await message.answer(f"Audit log за {days} дн. пуст.")
        return
    lines = [f"Audit log за {days} дн. Последние {len(rows)} записей:"]
    for row in rows:
        details = row.details or {}
        timestamp = row.timestamp.astimezone().strftime("%d.%m %H:%M") if row.timestamp else "—"
        result = details.get("result")
        target = details.get("target") or details.get("client") or details.get("telegram_id") or ""
        error = details.get("error")
        suffix_parts = []
        if target:
            suffix_parts.append(f"target={target}")
        if result:
            suffix_parts.append(f"result={result}")
        if error:
            suffix_parts.append(f"error={error}")
        suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
        lines.append(f"{timestamp} · {row.actor} · {row.action} · {row.entity}:{short_id(row.entity_id)}{suffix}")
    await send_admin_lines(message, lines)


@router.message(Command("retry_failed"))
async def admin_retry_failed(message: Message) -> None:
    if not await require_admin(message, "provision"):
        return
    args = command_args(message)
    try:
        limit = int(args[0]) if args else 25
    except ValueError:
        await message.answer("Использование: /retry_failed [limit]")
        return
    if limit < 1 or limit > 100:
        await message.answer("Лимит должен быть от 1 до 100.")
        return
    async with SessionLocal() as session:
        order_ids = list((await session.scalars(select(Order.id).where(Order.status == OrderStatus.PROVISIONING_FAILED).order_by(Order.created_at.asc()).limit(limit))).all())
    if not order_ids:
        await message.answer("Failed provisioning заказов нет.")
        return
    ok_count = 0
    fail_count = 0
    lines = [f"Повтор failed provisioning: найдено {len(order_ids)}"]
    for order_id in order_ids:
        async with SessionLocal() as session:
            try:
                subscription = await retry_failed_provisioning(session, settings, order_id)
                session.add(AuditLog(actor=f"admin:{message.from_user.id}", action="admin_retry_failed_batch", entity="order", entity_id=str(order_id), details={"result": "success"}))
                await session.commit()
                ok_count += 1
                lines.append(f"✅ {short_id(order_id)}: ACTIVE до {subscription.expires_at.astimezone().strftime('%d.%m.%Y %H:%M')}")
            except Exception as exc:
                await session.rollback()
                fail_count += 1
                log.exception("admin_retry_failed_batch_item_failed", order_id=str(order_id))
                lines.append(f"❌ {short_id(order_id)}: {type(exc).__name__}")
    lines.insert(1, f"Итог: успешно {ok_count}, ошибок {fail_count}")
    await send_admin_lines(message, lines)


@router.message(Command("node"))
async def admin_node(message: Message) -> None:
    if not await require_admin(message):
        return
    args = command_args(message)
    if len(args) != 1:
        await message.answer("Использование: /node <name>")
        return
    needle = args[0].lower()
    try:
        client = RemnawaveClient(settings)
        nodes = await client.list_nodes()
        hosts = await client.list_hosts()
    except Exception:
        log.exception("admin_node_failed")
        await message.answer("Не удалось получить данные Remnawave.")
        return
    matches = [node for node in nodes if needle in str(node.get("name", "")).lower()]
    if not matches:
        await message.answer("Нода не найдена. Используйте /nodes для списка.")
        return
    node = matches[0]
    node_uuid = str(node.get("uuid") or node.get("id") or "")
    node_hosts = [host for host in hosts if node_uuid and node_uuid in host_node_ids(host)]
    lines = [
        f"Карточка ноды: {node.get('name', '?')}",
        f"Статус: {ok_bad(bool(node.get('isConnected')))} {'connected' if node.get('isConnected') else 'disconnected'}",
        f"UUID/ID: {node_uuid or '?'}",
        f"Страна: {node.get('countryCode') or '?'}",
        f"Версия: {node.get('version') or node.get('nodeVersion') or '?'}",
        f"Трафик: {node.get('trafficUsedBytes') or node.get('traffic') or '?'}",
    ]
    if node_hosts:
        lines.append("Hosts:")
        for host in node_hosts:
            remark = host.get("remark") or host.get("name") or "host"
            lines.append(f"- {remark}: {host.get('address', '?')}:{host.get('port', '?')}")
    else:
        lines.append("Hosts: не найдены")
    await send_admin_lines(message, lines)


@router.message(Command("remnawave_sync"))
async def admin_remnawave_sync(message: Message) -> None:
    if not await require_admin(message, "ops"):
        return
    args = command_args(message)
    if args and args != ["report"]:
        await message.answer("Использование: /remnawave_sync\nСейчас команда работает в безопасном report-only режиме.")
        return
    try:
        registry = load_node_registry()
        client = RemnawaveClient(settings)
        nodes, hosts = await asyncio.gather(client.list_nodes(), client.list_hosts())
    except Exception as exc:
        log.exception("admin_remnawave_sync_failed")
        await message.answer(f"Не удалось выполнить сверку Remnawave registry: {type(exc).__name__}")
        return
    active_count = sum(1 for node in registry.get("nodes", []) if node.get("status") == "active")
    drift = compare_registry_to_remnawave(registry, nodes, hosts)
    lines = summarize_drift(drift, registry_count=active_count, nodes_count=len(nodes), hosts_count=len(hosts))
    await send_admin_lines(message, lines)


@router.message(Command("payments"))
async def admin_payments(message: Message) -> None:
    if not await require_admin(message, "billing"):
        return
    args = command_args(message)
    try:
        days = int(args[0]) if args else 30
    except ValueError:
        await message.answer("Использование: /payments [дни]")
        return
    if days < 1 or days > 365:
        await message.answer("Период должен быть от 1 до 365 дней.")
        return
    since = datetime.now(UTC) - timedelta(days=days)
    query = (
        select(Payment, Order, Plan, Customer)
        .join(Order, Order.id == Payment.order_id)
        .join(Plan, Plan.id == Order.plan_id)
        .join(Customer, Customer.id == Order.customer_id)
        .where(Order.created_at >= since)
        .order_by(Order.created_at.desc())
        .limit(20)
    )
    async with SessionLocal() as session:
        rows = (await session.execute(query)).all()
    if not rows:
        await message.answer("Оплат за выбранный период нет.")
        return
    lines = [f"Последние оплаты за {days} дн.:"]
    for payment, order, plan, customer in rows:
        paid_at = payment.paid_at.astimezone().strftime("%d.%m %H:%M") if payment.paid_at else "не оплачено"
        payment_ref = short_id(payment.yookassa_payment_id)
        lines.append(f"{paid_at} · {customer_label(customer)} · {plan.name} · {payment.amount:.2f} ₽ · {payment.status} · pay:{payment_ref} · order:{short_id(order.id)}")
    await send_admin_lines(message, lines)


@router.message(Command("finance"))
async def admin_finance(message: Message) -> None:
    if not await require_admin(message, "billing"):
        return
    args = command_args(message)
    try:
        days = int(args[0]) if args else 30
    except ValueError:
        await message.answer("Использование: /finance [дни]")
        return
    if days < 1 or days > 365:
        await message.answer("Период должен быть от 1 до 365 дней.")
        return
    try:
        async with SessionLocal() as session:
            lines, _issues = await reconcile_yookassa_finance(session, settings, days=days, limit=200)
    except Exception as exc:
        log.exception("admin_finance_failed")
        await message.answer(f"Не удалось выполнить финансовую сверку: {type(exc).__name__}")
        return
    await send_admin_lines(message, lines)


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
    telegram_id = callback.from_user.id
    telegram_username = f"@{callback.from_user.username}" if callback.from_user.username else None
    async with SessionLocal() as session:
        customer = await session.scalar(select(Customer).where(Customer.telegram_id == telegram_id))
        email = customer.email if customer else f"telegram-{telegram_id}@users.alanet.ru"
    try:
        async with SessionLocal() as session:
            order, confirmation_url, _bind_url = await create_checkout(
                session,
                settings,
                plan_slug=plan.slug,
                email=email,
                telegram_username=telegram_username,
                telegram_id=telegram_id,
            )
    except ValueError:
        await answer_callback(callback, "Тариф недоступен. Начните оформление заново.", reply_markup=main_menu())
        return
    except Exception:
        log.exception("telegram_checkout_failed", telegram_id=telegram_id)
        await answer_callback(callback, "Платёжный сервис временно недоступен. Попробуйте позже.", reply_markup=main_menu())
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Оплатить", url=confirmation_url)]]
    )
    await answer_callback(
        callback,
        f"Вы выбрали «{plan.name}» за {plan.price_rub:.0f} ₽. Заказ создан — нажмите кнопку ниже для безопасной оплаты.",
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
