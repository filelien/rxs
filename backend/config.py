from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: str = "development"
    app_secret_key: str = "raxus-dev-secret-key-change-in-production-32c"
    app_debug: bool = False
    app_cors_origins: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # MySQL Applicative (base principale de Raxus)
    app_db_host: str = "localhost"
    app_db_port: int = 3306
    app_db_user: str = "raxus"
    app_db_password: str = "change-me"
    app_db_name: str = "raxus_app"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""

    # JWT
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # LLM
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-20250514"

    # Encryption
    credentials_encryption_key: str = "raxus-dev-fernet-key-32bytes-pad!"

    # Monitoring
    metrics_scrape_interval_seconds: int = 30
    slow_query_threshold_ms: int = 1000

    # Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Raxus <noreply@raxus.io>"
    slack_webhook_url: str = ""
    alert_webhook_url: str = ""

    # Grafana
    grafana_password: str = "raxus-grafana"

    @field_validator("app_cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",")]
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
