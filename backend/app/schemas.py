from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class CheckoutRequest(BaseModel):
    plan_slug: str = Field(min_length=1, max_length=64)
    email: EmailStr
    telegram_username: str | None = Field(default=None, max_length=64)


class CheckoutResponse(BaseModel):
    order_id: str
    confirmation_url: str
    telegram_bind_url: str | None = None


class RenewalCheckoutRequest(BaseModel):
    plan_slug: Literal["start", "calm", "year"]


class BindTelegramRequest(BaseModel):
    token: str = Field(min_length=32, max_length=128)


class TelegramSessionExchangeRequest(BaseModel):
    token: str = Field(min_length=32, max_length=160)
