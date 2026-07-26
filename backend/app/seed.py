import asyncio
from decimal import Decimal
from sqlalchemy import select
from .config import get_settings
from .db import SessionLocal
from .models import Plan

PLANS = [
    {"slug": "start", "name": "Старт", "duration_days": 30, "traffic_limit_bytes": 0, "device_limit": 1, "price_rub": Decimal("299.00")},
    {"slug": "calm", "name": "Спокойно", "duration_days": 90, "traffic_limit_bytes": 0, "device_limit": 1, "price_rub": Decimal("749.00")},
    {"slug": "year", "name": "На год", "duration_days": 365, "traffic_limit_bytes": 1024 * 1024**3, "device_limit": 5, "price_rub": Decimal("2490.00")},
]


async def seed() -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        for values in PLANS:
            plan = await session.scalar(select(Plan).where(Plan.slug == values["slug"]))
            if plan:
                for key, value in values.items():
                    setattr(plan, key, value)
                plan.remnawave_squad_id = settings.remnawave_squad_id
            else:
                session.add(Plan(**values, remnawave_squad_id=settings.remnawave_squad_id))
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
