"""Map OpenAI client failures to application errors without leaking payloads."""

from __future__ import annotations

from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError

from calorie_bot.app.exceptions import ErrorCode, OpenAIServiceError


def translate_openai_exception(exc: Exception) -> OpenAIServiceError:
    """Convert an OpenAI SDK error into a safe ``OpenAIServiceError``."""
    if isinstance(exc, RateLimitError):
        return OpenAIServiceError(ErrorCode.OPENAI_RATE_LIMIT, log_hint="openai_rate_limit")
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return OpenAIServiceError(ErrorCode.OPENAI_UNAVAILABLE, log_hint=type(exc).__name__)
    if isinstance(exc, APIError):
        # Do not forward status body to users or logs verbatim.
        return OpenAIServiceError(
            ErrorCode.OPENAI_UNAVAILABLE,
            log_hint=f"api_error_{getattr(exc, 'status_code', 'unknown')}",
        )
    return OpenAIServiceError(ErrorCode.OPENAI_UNAVAILABLE, log_hint=type(exc).__name__)
