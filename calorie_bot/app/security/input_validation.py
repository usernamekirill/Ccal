"""Centralized media and text checks for handlers (raise ``ValidationError``)."""

from __future__ import annotations

from calorie_bot.app.exceptions import ErrorCode, ValidationError


def ensure_photo_size(file_size: int | None, max_bytes: int) -> None:
    """Reject oversized Telegram photos before download."""
    if file_size is not None and file_size > max_bytes:
        raise ValidationError(ErrorCode.FILE_TOO_LARGE, log_hint="photo_bytes")


def ensure_audio_duration(duration_sec: int | None, max_seconds: int) -> None:
    """Reject audio longer than configured maximum."""
    if duration_sec is not None and duration_sec > max_seconds:
        raise ValidationError(ErrorCode.AUDIO_TOO_LONG, log_hint="audio_duration")


def ensure_meal_text_length(text: str, max_chars: int) -> None:
    """Cap natural-language meal descriptions before LLM calls."""
    if len(text) > max_chars:
        raise ValidationError(ErrorCode.TEXT_TOO_LONG, log_hint="meal_text_len")
