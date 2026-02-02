# config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # tell pydantic-settings to read from .env
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

    # API
    api_title: str = "Partner Payout API"
    api_version: str = "1.0.0"

    # Environment (✅ add this to match ENVIRONMENT in .env)
    environment: str = "development"

    # Security
    executor_token: str
    api_key_hash_secret: str
    cors_origins: list[str] = ["*"]

    # Database
    database_url: str
    pool_size: int = 20
    max_overflow: int = 30
    pool_timeout: int = 30
    pool_recycle: int = 1800

    # Rate Limiting
    rate_limit_per_minute: int = 100
    rate_limit_per_day: int = 10000

    # Business Rules
    max_lease_seconds: int = 300
    max_batch_size: int = 10
    max_amount: float = 10000.0

@lru_cache()
def get_settings() -> Settings:
    return Settings()
