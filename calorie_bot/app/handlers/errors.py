import logging

from aiogram import Router
from aiogram.types import ErrorEvent

from calorie_bot.app.exceptions import UserFacingHandledError
from calorie_bot.app.messages import errors as error_messages

logger = logging.getLogger(__name__)
router = Router(name="errors")


@router.errors()
async def handle_error(event: ErrorEvent) -> bool:
    """Fallback when an error escapes the dispatcher error middleware."""
    if isinstance(event.exception, UserFacingHandledError):
        return True
    logger.exception(
        "Unhandled bot error (errors router): %s",
        type(event.exception).__name__,
    )
    if event.update.message:
        await event.update.message.answer(error_messages.DEFAULT_USER_ERROR)
    return True
