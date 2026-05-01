"""Per-user AI burst limits on routers that call OpenAI-backed handlers."""

from __future__ import annotations

from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from calorie_bot.app.exceptions import RateLimitError
from calorie_bot.app.ratelimit.sliding_window import SlidingWindowRateLimiter
from calorie_bot.app.states.meal import MealStates
from calorie_bot.app.states.settings import SettingsStates


class AIRateLimitMiddleware(BaseMiddleware):
    """Sliding-window cap on AI-backed updates per Telegram user id."""

    _SKIP_TEXT_STATES: frozenset[str | None] = frozenset(
        {
            SettingsStates.entering_calorie_goal.state,
            MealStates.photo_editing.state,
        },
    )

    def __init__(self, limiter: SlidingWindowRateLimiter) -> None:
        self._limiter = limiter

    async def __call__(
        self,
        handler: Any,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        telegram_id = getattr(user, "id", None)
        if telegram_id is None:
            return await handler(event, data)

        if isinstance(event, Message) and event.text:
            if event.text.startswith("/"):
                return await handler(event, data)
            raw_state = data.get("raw_state")
            if raw_state in self._SKIP_TEXT_STATES:
                return await handler(event, data)

        if not self._limiter.allow(int(telegram_id)):
            raise RateLimitError()
        return await handler(event, data)
