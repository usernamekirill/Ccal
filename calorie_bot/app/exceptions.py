"""Application-specific errors with stable codes for user-facing mapping."""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """Stable keys for centralized user messages and logging."""

    RATE_LIMIT_AI = "rate_limit_ai"
    FILE_TOO_LARGE = "file_too_large"
    UNSUPPORTED_IMAGE_FORMAT = "unsupported_image_format"
    TEXT_TOO_LONG = "text_too_long"
    AUDIO_TOO_LONG = "audio_too_long"
    OPENAI_UNAVAILABLE = "openai_unavailable"
    OPENAI_RATE_LIMIT = "openai_rate_limit"
    TELEGRAM_NETWORK = "telegram_network"
    TELEGRAM_BAD_REQUEST = "telegram_bad_request"
    TELEGRAM_SERVER = "telegram_server"
    DATABASE_ERROR = "database_error"
    UNKNOWN = "unknown"


class AppError(Exception):
    """Base error carrying a safe ``ErrorCode`` (never show stack traces to users)."""

    def __init__(self, code: ErrorCode, *, log_hint: str | None = None) -> None:
        self.code = code
        self.log_hint = log_hint
        super().__init__(code.value)


class RateLimitError(AppError):
    """Client exceeded AI request rate (sliding window)."""

    def __init__(self) -> None:
        super().__init__(ErrorCode.RATE_LIMIT_AI)


class ValidationError(AppError):
    """User input failed size/format/length checks."""

    def __init__(self, code: ErrorCode, *, log_hint: str | None = None) -> None:
        super().__init__(code, log_hint=log_hint)


class OpenAIServiceError(AppError):
    """Upstream OpenAI failure after redaction (no response body in message)."""

    def __init__(
        self,
        code: ErrorCode = ErrorCode.OPENAI_UNAVAILABLE,
        *,
        log_hint: str | None = None,
    ):
        super().__init__(code, log_hint=log_hint)


class TelegramUpstreamError(AppError):
    """Telegram Bot API transport or server issues."""

    def __init__(self, code: ErrorCode, *, log_hint: str | None = None) -> None:
        super().__init__(code, log_hint=log_hint)


class DatabaseUserError(AppError):
    """Masked database failure for end users."""

    def __init__(self) -> None:
        super().__init__(ErrorCode.DATABASE_ERROR)


class UserFacingHandledError(Exception):
    """User already saw a safe message; main request session must roll back."""

    pass
