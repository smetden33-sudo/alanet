from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .integrations.yookassa import YooKassaClient
from .models import Customer, Order, OrderStatus, Payment, Plan, Subscription, SubscriptionStatus


@dataclass(frozen=True)
class FinanceIssue:
    severity: str
    kind: str
    message: str


def _money(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _short(value: object) -> str:
    return str(value)[:8] if value is not None else "—"


def _customer_label(customer: Customer | None) -> str:
    if not customer:
        return "unknown"
    return customer.telegram_username or (f"TG {customer.telegram_id}" if customer.telegram_id else customer.email)


def payment_is_successful(status: str | None) -> bool:
    return str(status or "").lower() == "succeeded"


def order_is_active(status: OrderStatus | str | None) -> bool:
    value = status.value if isinstance(status, OrderStatus) else str(status or "")
    return value == OrderStatus.ACTIVE.value


async def reconcile_yookassa_finance(
    session: AsyncSession,
    settings: Settings,
    *,
    days: int = 30,
    limit: int = 200,
) -> tuple[list[str], list[FinanceIssue]]:
    """Compare local payments/orders/subscriptions with YooKassa.

    This is intentionally report-only. It must not activate or revoke access:
    commercial reconciliation should show anomalies first, then a human or a
    separate provisioning retry flow decides how to fix them.
    """

    if not settings.yookassa_enabled:
        return ["YooKassa financial reconciliation", "Status: skipped — YooKassa is disabled."], []

    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    query = (
        select(Payment, Order, Plan, Customer, Subscription)
        .join(Order, Order.id == Payment.order_id)
        .join(Plan, Plan.id == Order.plan_id)
        .join(Customer, Customer.id == Order.customer_id)
        .outerjoin(Subscription, Subscription.customer_id == Customer.id)
        .where(Order.created_at >= since)
        .order_by(Order.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(query)).all()
    client = YooKassaClient(settings)
    issues: list[FinanceIssue] = []
    checked_remote = 0
    remote_succeeded = 0
    local_succeeded = 0
    active_orders = 0

    for payment, order, plan, customer, subscription in rows:
        label = _customer_label(customer)
        local_payment_ok = payment_is_successful(payment.status)
        local_order_active = order_is_active(order.status)
        subscription_active = bool(subscription and subscription.status == SubscriptionStatus.ACTIVE)
        if local_payment_ok:
            local_succeeded += 1
        if local_order_active:
            active_orders += 1

        remote: dict[str, Any] | None = None
        if payment.yookassa_payment_id:
            try:
                remote = await client.get_payment(payment.yookassa_payment_id)
                checked_remote += 1
            except Exception as exc:
                severity = "critical" if local_payment_ok or local_order_active else "warning"
                issues.append(FinanceIssue(severity, "yookassa_lookup_failed", f"pay:{_short(payment.yookassa_payment_id)} order:{_short(order.id)} — YooKassa lookup failed: {type(exc).__name__}."))
        else:
            issues.append(FinanceIssue("warning", "missing_yookassa_payment_id", f"order:{_short(order.id)} {label} — local payment has no YooKassa payment ID."))

        if remote:
            remote_status = str(remote.get("status") or "")
            remote_amount = _money((remote.get("amount") or {}).get("value"))
            local_amount = _money(payment.amount)
            metadata = remote.get("metadata") or {}
            if remote_status == "succeeded":
                remote_succeeded += 1
            if remote_status != str(payment.status):
                issues.append(FinanceIssue("critical", "payment_status_mismatch", f"pay:{_short(payment.yookassa_payment_id)} {label} — local status {payment.status}, YooKassa status {remote_status}."))
            if remote_amount is not None and local_amount is not None and remote_amount != local_amount:
                issues.append(FinanceIssue("critical", "payment_amount_mismatch", f"pay:{_short(payment.yookassa_payment_id)} {label} — local amount {local_amount}, YooKassa amount {remote_amount}."))
            if str(metadata.get("order_id") or "") != str(order.id):
                issues.append(FinanceIssue("critical", "metadata_order_id_mismatch", f"pay:{_short(payment.yookassa_payment_id)} — metadata.order_id does not match local order {_short(order.id)}."))
            if str(metadata.get("customer_id") or "") != str(customer.id):
                issues.append(FinanceIssue("critical", "metadata_customer_id_mismatch", f"pay:{_short(payment.yookassa_payment_id)} — metadata.customer_id does not match local customer {_short(customer.id)}."))
            if str(metadata.get("plan_id") or "") != str(plan.id):
                issues.append(FinanceIssue("critical", "metadata_plan_id_mismatch", f"pay:{_short(payment.yookassa_payment_id)} — metadata.plan_id does not match local plan {plan.slug}."))

            if remote_status == "succeeded" and (not local_order_active or not subscription_active):
                issues.append(FinanceIssue("critical", "paid_not_active", f"pay:{_short(payment.yookassa_payment_id)} {label} — paid in YooKassa, but local order={order.status.value}, subscription={'ACTIVE' if subscription_active else 'not ACTIVE'}."))

        if local_order_active and not local_payment_ok and order.amount > 0:
            issues.append(FinanceIssue("critical", "active_without_succeeded_payment", f"order:{_short(order.id)} {label} — local order ACTIVE, but payment status is {payment.status}."))

    critical = sum(1 for item in issues if item.severity == "critical")
    warnings = sum(1 for item in issues if item.severity == "warning")
    revenue_local = sum((_money(payment.amount) or Decimal("0.00")) for payment, *_rest in rows if payment_is_successful(payment.status))
    lines = [
        "YooKassa financial reconciliation",
        f"Period: {since.astimezone().strftime('%d.%m %H:%M')} - {now.astimezone().strftime('%d.%m %H:%M')}",
        f"Local payments checked: {len(rows)}",
        f"YooKassa payments checked: {checked_remote}",
        f"Local succeeded: {local_succeeded}",
        f"YooKassa succeeded: {remote_succeeded}",
        f"Active orders: {active_orders}",
        f"Local succeeded revenue: {revenue_local:.2f} RUB",
        f"Issues: critical {critical}, warnings {warnings}",
    ]
    if not issues:
        lines.append("Status: ok — finance, YooKassa and provisioning states match.")
    else:
        lines.append("Status: attention required — report-only, no automatic access changes were made.")
        for item in issues[:40]:
            icon = "⛔" if item.severity == "critical" else "⚠️"
            lines.append(f"{icon} {item.kind}: {item.message}")
        if len(issues) > 40:
            lines.append(f"...and {len(issues) - 40} more issues.")
    return lines, issues
