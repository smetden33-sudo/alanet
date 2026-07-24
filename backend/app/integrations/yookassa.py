from decimal import Decimal
from typing import Any
import httpx
from ..config import Settings


class YooKassaError(RuntimeError):
    pass


class YooKassaClient:
    base_url = "https://api.yookassa.ru/v3"

    def __init__(self, settings: Settings):
        self.auth = (settings.yookassa_shop_id, settings.yookassa_secret_key.get_secret_value())
        self.vat_code = settings.yookassa_vat_code

    async def create_payment(self, *, order_id: str, customer_id: str, plan_id: str, amount: Decimal, email: str, return_url: str, idempotency_key: str) -> dict[str, Any]:
        payload = {
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": f"Доступ к сервису, заказ {order_id[:8]}",
            "metadata": {"order_id": order_id, "customer_id": customer_id, "plan_id": plan_id},
            "receipt": {"customer": {"email": email}, "items": [{"description": "Доступ к онлайн-сервису", "quantity": "1.00", "amount": {"value": f"{amount:.2f}", "currency": "RUB"}, "vat_code": self.vat_code, "payment_mode": "full_payment", "payment_subject": "service"}]},
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(f"{self.base_url}/payments", auth=self.auth, headers={"Idempotence-Key": idempotency_key}, json=payload)
        if response.status_code not in (200, 201):
            raise YooKassaError(f"payment creation failed: HTTP {response.status_code}")
        return response.json()

    async def get_payment(self, payment_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{self.base_url}/payments/{payment_id}", auth=self.auth)
        if response.status_code != 200:
            raise YooKassaError(f"payment lookup failed: HTTP {response.status_code}")
        return response.json()

    async def create_refund(self, *, payment_id: str, amount: Decimal, idempotency_key: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(f"{self.base_url}/refunds", auth=self.auth, headers={"Idempotence-Key": idempotency_key}, json={"payment_id": payment_id, "amount": {"value": f"{amount:.2f}", "currency": "RUB"}})
        if response.status_code not in (200, 201):
            raise YooKassaError(f"refund failed: HTTP {response.status_code}")
        return response.json()
