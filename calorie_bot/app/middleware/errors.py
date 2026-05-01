"""Global error handling: friendly replies, safe logs, no stack traces to users."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramServerError
from aiogram.types import CallbackQuery, Message, TelegramObject, Update
from sqlalchemy.exc import SQLAlchemyError

from calorie_bot.app.exceptions import (
    AppError,
    DatabaseUserError,
    ErrorCode,
    TelegramUpstreamError,
    UserFacingHandledError,
)
from calorie_bot.app.messages import errors as error_messages
from calorie_bot.app.repositories.error_log_repository import ErrorLogRepository
from calorie_bot.app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


def _resolve_message(event: TelegramObject) -> Message | None:
    """Best-effort ``Message`` to reply on for routed updates."""
    if isinstance(event, Message):
        return event
    if isinstance(event, CallbackQuery):
        return event.message
    if isinstance(event, Update):
        if event.message:
            return event.message
        if event.edited_message:
            return event.edited_message
        if event.callback_query and event.callback_query.message:
            return event.callback_query.message
    return None


def _map_to_app_error(exc: BaseException) -> tuple[AppError, bool]:
    """Return (normalized_error, was_already_app_error)."""
    if isinstance(exc, AppError):
        return exc, True
    if isinstance(exc, TelegramNetworkError):
        return (
            TelegramUpstreamError(ErrorCode.TELEGRAM_NETWORK, log_hint=type(exc).__name__),
            False,
        )
    if isinstance(exc, TelegramBadRequest):
        return (
            TelegramUpstreamError(ErrorCode.TELEGRAM_BAD_REQUEST, log_hint=type(exc).__name__),
            False,
        )
    if isinstance(exc, TelegramServerError):
        return (
            TelegramUpstreamError(ErrorCode.TELEGRAM_SERVER, log_hint=type(exc).__name__),
            False,
        )
    if isinstance(exc, SQLAlchemyError):
        return (DatabaseUserError(), False)

    from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError

    if isinstance(
        exc,
        (APIError, APIConnectionError, APITimeoutError, RateLimitError),
    ):
        from calorie_bot.app.utils.openai_errors import translate_openai_exception

        return (translate_openai_exception(exc), False)
    unknown = AppError(ErrorCode.UNKNOWN, log_hint=type(exc).__name__)
    return (unknown, False)


class ErrorHandlerMiddleware(BaseMiddleware):
    """Catch failures from inner middlewares and handlers; never leak traces to chats."""

    async def __call__(
        self,
        handler: Any,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:
            app_exc, already_app = _map_to_app_error(exc)
            await self._notify_user(event, data, app_exc)
            await self._persist_safe_log(data, app_exc, original_type=type(exc).__name__)
            if isinstance(exc, SQLAlchemyError):
                logger.exception("database_error type=%s", type(exc).__name__)
            elif already_app:
                logger.warning(
                    "handled_app_error code=%s hint=%s",
                    app_exc.code.value,
                    app_exc.log_hint,
                )
            elif isinstance(
                exc,
                (TelegramNetworkError, TelegramBadRequest, TelegramServerError),
            ):
                logger.warning("telegram_error type=%s", type(exc).__name__)
            elif type(exc).__module__.startswith("openai"):
                logger.warning("openai_client_error type=%s", type(exc).__name__)
            else:
                logger.exception(
                    "unexpected_error type=%s mapped=%s",
                    type(exc).__name__,
                    app_exc.code.value,
                )
            raise UserFacingHandledError() from None

    async def _notify_user(
        self,
        event: TelegramObject,
        data: dict[str, Any],
        app_exc: AppError,
    ) -> None:
        text = error_messages.text_for_app_error(app_exc)
        msg = _resolve_message(event)
        bot: Bot | None = data.get("bot")
        if msg and bot:
            try:
                await msg.answer(text)
                return
            except Exception as send_exc:
                logger.warning("error_reply_failed type=%s", type(send_exc).__name__)
        if isinstance(event, Update) and event.callback_query and bot:
            try:
                await event.callback_query.answer(text[:200], show_alert=True)
            except Exception:
                pass
        elif isinstance(event, CallbackQuery) and bot:
            try:
                await event.answer(text[:200], show_alert=True)
            except Exception:
                pass

    async def _persist_safe_log(
        self,
        data: dict[str, Any],
        app_exc: AppError,
        *,
        original_type: str,
    ) -> None:
        factory = data.get("_session_factory")
        if factory is None:
            return
        tg_user = data.get("event_from_user")
        telegram_id = getattr(tg_user, "id", None)
        internal_id: int | None = None
        safe = f"{original_type}->{app_exc.code.value}"
        if app_exc.log_hint:
            safe = f"{safe}:{app_exc.log_hint}"
        try:
            async with factory() as s:
                if telegram_id is not None:
                    user_row = await UserRepository(s).get_by_telegram_id(int(telegram_id))
                    if user_row:
                        internal_id = user_row.id
                await ErrorLogRepository(s).create_safe_log(
                    error_type=original_type,
                    user_id=internal_id,
                    handler="ErrorHandlerMiddleware",
                    safe_message=safe[:512],
                )
                await s.commit()
        except SQLAlchemyError:
            logger.warning("error_log_persist_skipped")
