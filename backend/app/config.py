from functools import lru_cache
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://billing:billing@postgres:5432/billing"
    redis_url: str = "redis://redis:6379/0"
    public_api_url: str = "http://localhost:8000"
    public_site_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"
    yookassa_shop_id: str = ""
    yookassa_secret_key: SecretStr = SecretStr("")
    yookassa_vat_code: int = 1
    remnawave_base_url: str = "http://remnawave:3000"
    remnawave_token: SecretStr = SecretStr("")
    remnawave_squad_id: str = ""
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_webhook_secret: SecretStr = SecretStr("")
    telegram_admin_chat_id: int | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
