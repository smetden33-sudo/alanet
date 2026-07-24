from datetime import UTC, datetime, timedelta
from app.services import extended_expiry


def test_extends_active_subscription_from_current_expiry():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    current = now + timedelta(days=10)
    assert extended_expiry(current, 30, now) == now + timedelta(days=40)


def test_extends_expired_subscription_from_now():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    current = now - timedelta(days=1)
    assert extended_expiry(current, 30, now) == now + timedelta(days=30)
