"""Compose consistent post-save and post-action Telegram replies."""

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.config import Settings
from calorie_bot.app.keyboards.confirmation import after_meal_saved_keyboard
from calorie_bot.app.messages.ux_flow import (
    POST_SAVE_CONFIRMED_HEAD,
    POST_SAVE_WHAT_NEXT,
)
from calorie_bot.app.repositories.profile_repository import ProfileRepository
from calorie_bot.app.repositories.stats_repository import StatsRepository
from calorie_bot.app.services.stats_service import StatsService
from calorie_bot.app.stats.formatting import format_today_status_line


async def send_post_action_message(
    message: Message,
    *,
    session: AsyncSession,
    settings: Settings,
    user_id: int,
    meal_brief_text: str,
    edit_in_place: bool = False,
) -> None:
    """After a successful save: result, day status, explicit next step, and inline CTAs.

    Does not send motivation — callers can follow with ``answer(..., reply_markup=...)``.
    """
    stats_service = StatsService(
        stats_repository=StatsRepository(session),
        profile_repository=ProfileRepository(session),
        default_timezone=settings.timezone,
    )
    today = await stats_service.today_view(user_id)
    status = format_today_status_line(today)
    text = "\n\n".join(
        [
            POST_SAVE_CONFIRMED_HEAD,
            meal_brief_text,
            status,
            POST_SAVE_WHAT_NEXT,
        ]
    )
    keyboard = after_meal_saved_keyboard()
    if edit_in_place:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)
