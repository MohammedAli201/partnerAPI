# config.py
from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr
from decimal import Decimal

class Settings(BaseSettings):
    # ✅ UI login session settings
    secret_key: str = Field(alias="SECRET_KEY")
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    partner_fee: Decimal = Field(default=Decimal('0.60'), alias="PARTNER_FEE")
    reporting_timezone: str = Field(default='UTC', alias='REPORTING_TIMEZONE')
    fee_policy_version: str = Field(default='fixed-success-v1', alias='FEE_POLICY_VERSION')

    # read .env locally, but in Fly it will read from real environment variables
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="forbid")

    payout_status_webhook_url: str = Field(
        default="http://localhost:5269/api/webhooks/payout-status",
        alias="PAYOUT_STATUS_WEBHOOK_URL",
    )
    payout_status_webhook_secret: SecretStr = Field(
        default=SecretStr(""), alias="PAYOUT_STATUS_WEBHOOK_SECRET"
    )
    payout_status_webhook_auth_mode: Literal["hmac", "api_key"] = Field(
        default="hmac", alias="PAYOUT_STATUS_WEBHOOK_AUTH_MODE"
    )
    payout_status_webhook_api_key: SecretStr = Field(
        default=SecretStr(""), alias="PAYOUT_STATUS_WEBHOOK_API_KEY"
    )

    # API
    api_title: str = "Partner Payout API"
    api_version: str = "1.0.0"

    # Environment
    environment: str = Field(default="development", alias="ENVIRONMENT")

    # Security (map Fly secrets)
    executor_token: str = Field(alias="EXECUTOR_TOKEN")
    api_key_hash_secret: str = Field(alias="API_KEY_HASH_SECRET")
    cors_origins: list[str] = []

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
    max_amount: Decimal = Field(default=Decimal('10000.00'), alias="MAX_AMOUNT")
    api_key_verifier_secret: SecretStr = Field(default=SecretStr(''),alias='API_KEY_VERIFIER_SECRET')
    embedded_payment_workers: bool = Field(default=False,alias='EMBEDDED_PAYMENT_WORKERS')

@lru_cache()
def get_settings() -> Settings:
    return Settings()
