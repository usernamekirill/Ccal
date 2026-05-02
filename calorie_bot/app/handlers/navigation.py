"""Handlers for navigation callbacks (hints and hub) without touching domain state."""

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.config import Settings
from calorie_bot.app.keyboards.callback_data import NavCallback
from calorie_bot.app.keyboards.confirmation import help_screen_keyboard
from calorie_bot.app.keyboards.main_menu import primary_menu_keyboard
from calorie_bot.app.messages.ux_flow import (
    HOW_TO_ADD_EXPLANATION,
    MAIN_MENU_TITLE,
    READY_TO_LOG_BLURB,
)
from calorie_bot.app.repositories.profile_repository import ProfileRepository
from calorie_bot.app.repositories.stats_repository import StatsRepository
from calorie_bot.app.services.stats_service import StatsService
from calorie_bot.app.services.user_service import UserService
from calorie_bot.app.stats.formatting import format_today_status_line
from calorie_bot.app.texts.help import HELP_SCREEN_TEXT

router = Router(name="navigation")

_NAV_ADD_ALIASES = frozenset(
    {
        NavCallback.ADD_FOOD,
        NavCallback.HOW_TO_ADD_FOOD,
        NavCallback.ADD_VOICE_HINT,
        NavCallback.ADD_TEXT_HINT,
    }
)


def _stats(session: AsyncSession, settings: Settings) -> StatsService:
    """Build stats service for the active request."""
    return StatsService(
        stats_repository=StatsRepository(session),
        profile_repository=ProfileRepository(session),
        default_timezone=settings.timezone,
    )


@router.callback_query(F.data.in_(_NAV_ADD_ALIASES))
async def nav_how_to_add_food(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Explain native input: user sends photo, voice, or text — no mode switch."""
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    view = await _stats(session, settings).today_view(user.id)
    line = format_today_status_line(view)
    await callback.message.answer(
        f"{line}\n\n{HOW_TO_ADD_EXPLANATION}",
        reply_markup=primary_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == NavCallback.HELP)
async def nav_help(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Show help: native input, examples; menu + home afterwards."""
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    await UserService(session).ensure_user(callback.from_user)
    await callback.message.answer(HELP_SCREEN_TEXT, reply_markup=help_screen_keyboard())
    await callback.answer()


@router.callback_query(F.data == NavCallback.MAIN_MENU)
async def nav_main_menu(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Return to the hub menu with a short logging reminder."""
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    view = await _stats(session, settings).today_view(user.id)
    line = format_today_status_line(view)
    text = f"{line}\n\n{READY_TO_LOG_BLURB}\n\n{MAIN_MENU_TITLE}"
    await callback.message.edit_text(text, reply_markup=primary_menu_keyboard())
    await callback.answer()
