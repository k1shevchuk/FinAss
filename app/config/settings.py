from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_mode: Literal["polling", "webhook"] = "polling"
    log_level: str = "INFO"
    json_logs: bool = True

    telegram_bot_token: SecretStr = Field(alias="TELEGRAM_BOT_TOKEN")
    webhook_secret_token: SecretStr | None = Field(default=None, alias="WEBHOOK_SECRET_TOKEN")
    base_url: str | None = Field(default=None, alias="BASE_URL")

    google_service_account_json_path: Path | None = Field(
        default=None, alias="GOOGLE_SERVICE_ACCOUNT_JSON_PATH"
    )
    google_application_credentials: Path | None = Field(
        default=None, alias="GOOGLE_APPLICATION_CREDENTIALS"
    )
    google_drive_parent_folder_id: str | None = Field(
        default=None,
        alias="GOOGLE_DRIVE_PARENT_FOLDER_ID",
    )

    db_dsn: str = Field(alias="DB_DSN")
    redis_url: str = Field(alias="REDIS_URL")

    default_currency: str = Field(default="RUB", alias="DEFAULT_CURRENCY")
    default_timezone: str = Field(default="Europe/Berlin", alias="DEFAULT_TIMEZONE")
    default_rounding_mode: str = Field(default="HALF_UP", alias="DEFAULT_ROUNDING_MODE")

    invite_ttl_seconds: int = Field(default=3600, alias="INVITE_TTL_SECONDS")
    idempotency_ttl_seconds: int = Field(default=3600, alias="IDEMPOTENCY_TTL_SECONDS")

    rate_limit_user_per_min: int = Field(default=20, alias="RATE_LIMIT_USER_PER_MIN")
    rate_limit_chat_per_min: int = Field(default=60, alias="RATE_LIMIT_CHAT_PER_MIN")
    rate_limit_scan_per_10min: int = Field(default=5, alias="RATE_LIMIT_SCAN_PER_10MIN")

    qr_max_file_size_bytes: int = Field(default=5 * 1024 * 1024, alias="QR_MAX_FILE_SIZE_BYTES")
    qr_max_pixels: int = Field(default=12_000_000, alias="QR_MAX_PIXELS")
    qr_decode_timeout_seconds: int = Field(default=5, alias="QR_DECODE_TIMEOUT_SECONDS")
    telegram_download_timeout_seconds: int = Field(
        default=15, alias="TELEGRAM_DOWNLOAD_TIMEOUT_SECONDS"
    )

    google_api_retry_max_attempts: int = Field(default=5, alias="GOOGLE_API_RETRY_MAX_ATTEMPTS")
    google_api_retry_base_delay_seconds: float = Field(
        default=0.5, alias="GOOGLE_API_RETRY_BASE_DELAY_SECONDS"
    )
    google_api_retry_max_delay_seconds: float = Field(
        default=10, alias="GOOGLE_API_RETRY_MAX_DELAY_SECONDS"
    )

    cache_ttl_seconds: int = Field(default=300, alias="CACHE_TTL_SECONDS")
    report_cache_ttl_seconds: int = Field(default=120, alias="REPORT_CACHE_TTL_SECONDS")

    sentry_dsn: SecretStr | None = Field(default=None, alias="SENTRY_DSN")

    @property
    def google_credentials_path(self) -> Path:
        if self.google_service_account_json_path:
            return self.google_service_account_json_path
        if self.google_application_credentials:
            return self.google_application_credentials
        raise ValueError(
            "Set GOOGLE_SERVICE_ACCOUNT_JSON_PATH or GOOGLE_APPLICATION_CREDENTIALS in environment."
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
