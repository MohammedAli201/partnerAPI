# config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # ✅ UI login session settings
    secret_key: str = Field(alias="SECRET_KEY")
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    partner_fee: float = Field(default=0.60, alias="PARTNER_FEE")

    # read .env locally, but in Fly it will read from real environment variables
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

    # API
    api_title: str = "Partner Payout API"
    api_version: str = "1.0.0"

    # Environment
    environment: str = Field(default="development", alias="ENVIRONMENT")

    # Security (map Fly secrets)
    executor_token: str = Field(alias="EXECUTOR_TOKEN")
    api_key_hash_secret: str = Field(alias="API_KEY_HASH_SECRET")
    cors_origins: list[str] = ["*"]

    # Database (map Fly secret)
    database_url: str = Field(alias="DATABASE_URL")

    pool_size: int = 20
    max_overflow: int = 30
    pool_timeout: int = 30
    pool_recycle: int = 1800

    # Rate Limiting
    rate_limit_per_minute: int = Field(default=100, alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_per_day: int = Field(default=10000, alias="RATE_LIMIT_PER_DAY")

    # Business Rules
    max_lease_seconds: int = Field(default=300, alias="MAX_LEASE_SECONDS")
    max_batch_size: int = Field(default=10, alias="MAX_BATCH_SIZE")
    max_amount: float = Field(default=10000.0, alias="MAX_AMOUNT")

@lru_cache()
def get_settings() -> Settings:
    return Settings()
