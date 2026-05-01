from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    telegram_bot_token: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "BOT_TOKEN"),
    )
    openai_api_key: SecretStr = Field(default=SecretStr(""), alias="OPENAI_API_KEY")
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/calorie_bot.db",
        alias="DATABASE_URL",
    )
    app_env: str = Field(default="local", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    timezone: str = Field(default="Europe/Moscow", alias="TIMEZONE")
    max_photo_bytes: int = Field(default=5 * 1024 * 1024, alias="MAX_PHOTO_BYTES")
    max_audio_bytes: int = Field(default=10 * 1024 * 1024, alias="MAX_AUDIO_BYTES")
    max_audio_seconds: int = Field(default=60, alias="MAX_AUDIO_SECONDS")
    max_image_side_px: int = Field(default=1280, alias="MAX_IMAGE_SIDE_PX")
    image_jpeg_quality: int = Field(default=85, alias="IMAGE_JPEG_QUALITY")
    openai_timeout_seconds: int = Field(default=45, alias="OPENAI_TIMEOUT_SECONDS")
    ai_daily_soft_limit: int = Field(default=50, alias="AI_DAILY_SOFT_LIMIT")
    openai_vision_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_VISION_MODEL")
    openai_correction_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_CORRECTION_MODEL")
    openai_speech_model: str = Field(default="whisper-1", alias="OPENAI_SPEECH_MODEL")
    temp_media_dir: str = Field(default="./tmp", alias="TEMP_MEDIA_DIR")
    max_meal_text_chars: int = Field(default=3500, alias="MAX_MEAL_TEXT_CHARS")
    ai_rate_limit_per_minute: int = Field(default=18, alias="AI_RATE_LIMIT_PER_MINUTE")
    health_check_host: str = Field(default="127.0.0.1", alias="HEALTH_CHECK_HOST")
    # --- Storage backend (sqlite | postgres | external REST) ---
    database_type: str = Field(default="sqlite", alias="DATABASE_TYPE")
    postgres_pool_size: int = Field(default=5, alias="POSTGRES_POOL_SIZE")
    postgres_max_overflow: int = Field(default=10, alias="POSTGRES_MAX_OVERFLOW")

    external_storage_base_url: str = Field(default="", alias="EXTERNAL_STORAGE_BASE_URL")
    external_storage_api_key: SecretStr = Field(
        default=SecretStr(""),
        alias="EXTERNAL_STORAGE_API_KEY",
    )
    external_storage_timeout_seconds: float = Field(
        default=2.0,
        alias="EXTERNAL_STORAGE_TIMEOUT_SECONDS",
    )
    external_storage_max_retries: int = Field(default=2, alias="EXTERNAL_STORAGE_MAX_RETRIES")

    stats_cache_ttl_seconds: float = Field(default=0.0, alias="STATS_CACHE_TTL_SECONDS")
    health_check_port: int = Field(default=0, alias="HEALTH_CHECK_PORT")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def zoneinfo(self) -> ZoneInfo:
        """Return configured application timezone."""
        return ZoneInfo(self.timezone)


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
