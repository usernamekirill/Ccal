"""Tests for rate limiting, error copy, input guards, OpenAI mapping, and health HTTP."""

import asyncio

import pytest

from calorie_bot.app.exceptions import ErrorCode, ValidationError
from calorie_bot.app.messages import errors as err_pkg
from calorie_bot.app.ratelimit.sliding_window import SlidingWindowRateLimiter
from calorie_bot.app.security.input_validation import ensure_meal_text_length
from calorie_bot.app.utils.openai_errors import translate_openai_exception


def test_sliding_window_blocks_overflow() -> None:
    """Fourth event in the same minute should be rejected."""
    lim = SlidingWindowRateLimiter(max_events=3, window_sec=60.0)
    assert lim.allow(42, now=100.0) is True
    assert lim.allow(42, now=101.0) is True
    assert lim.allow(42, now=102.0) is True
    assert lim.allow(42, now=103.0) is False


def test_sliding_window_resets_after_window() -> None:
    """Old timestamps should fall out of the deque."""
    lim = SlidingWindowRateLimiter(max_events=2, window_sec=10.0)
    assert lim.allow(7, now=0.0) is True
    assert lim.allow(7, now=1.0) is True
    assert lim.allow(7, now=11.0) is True


def test_all_error_codes_have_user_text() -> None:
    """Every ``ErrorCode`` must map to a safe string."""
    for code in ErrorCode:
        assert code.value in err_pkg.USER_ERROR_TEXT
        assert len(err_pkg.USER_ERROR_TEXT[code.value]) > 5


def test_meal_text_length_guard() -> None:
    """Long free text should raise ``ValidationError``."""
    with pytest.raises(ValidationError) as exc:
        ensure_meal_text_length("a" * 5000, max_chars=100)
    assert exc.value.code == ErrorCode.TEXT_TOO_LONG


def test_translate_unknown_openai_exception() -> None:
    """Non-specific errors still become a safe OpenAI bucket."""
    out = translate_openai_exception(RuntimeError("secret_details"))
    assert out.code == ErrorCode.OPENAI_UNAVAILABLE
    assert "secret" not in (out.log_hint or "").lower()


@pytest.mark.asyncio
async def test_health_server_returns_200_ok() -> None:
    """GET /health should return a minimal HTTP 200 and body ``ok``."""
    from calorie_bot.app.health.server import handle_health_client

    server = await asyncio.start_server(handle_health_client, "127.0.0.1", 0)
    sock = server.sockets[0]
    host, port = sock.getsockname()[:2]
    async with server:
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(b"GET /health HTTP/1.0\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        data = await asyncio.wait_for(reader.read(512), timeout=2.0)
        writer.close()
        await writer.wait_closed()
    assert b"200 OK" in data
    assert b"ok" in data
