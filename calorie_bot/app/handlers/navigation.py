"""Handlers for navigation callbacks (hints and hub) without touching domain state."""

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.config import Settings
from calorie_bot.app.keyboards.callback_data import NavCallback
from calorie_bot.app.keyboards.confirmation import after_meal_saved_keyboard
from calorie_bot.app.keyboards.main_menu import primary_menu_keyboard
from calorie_bot.app.messages.ux_flow import (
    ADD_FOOD_GATEWAY_TEXT,
    ADD_TEXT_GATEWAY_TEXT,
    ADD_VOICE_GATEWAY_TEXT,
    MAIN_MENU_TITLE,
)
from calorie_bot.app.repositories.profile_repository import ProfileRepository
from calorie_bot.app.repositories.stats_repository import StatsRepository
from calorie_bot.app.services.stats_service import StatsService
from calorie_bot.app.services.user_service import UserService
from calorie_bot.app.stats.formatting import format_today_status_line

router = Router(name="navigation")


def _stats(session: AsyncSession, settings: Settings) -> StatsService:
    """Build stats service for the active request."""
    return StatsService(
        stats_repository=StatsRepository(session),
        profile_repository=ProfileRepository(session),
        default_timezone=settings.timezone,
    )


@router.callback_query(F.data == NavCallback.ADD_FOOD)
async def nav_add_food(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Tell the user how to log the next meal (photo / voice / text)."""
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    view = await _stats(session, settings).today_view(user.id)
    line = format_today_status_line(view)
    await callback.message.answer(
        f"{line}\n\n{ADD_FOOD_GATEWAY_TEXT}",
        reply_markup=after_meal_saved_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == NavCallback.ADD_VOICE_HINT)
async def nav_add_voice_hint(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Prompt for a voice meal log."""
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    view = await _stats(session, settings).today_view(user.id)
    line = format_today_status_line(view)
    await callback.message.answer(
        f"{line}\n\n{ADD_VOICE_GATEWAY_TEXT}",
        reply_markup=after_meal_saved_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == NavCallback.ADD_TEXT_HINT)
async def nav_add_text_hint(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Prompt for a text meal log."""
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    view = await _stats(session, settings).today_view(user.id)
    line = format_today_status_line(view)
    await callback.message.answer(
        f"{line}\n\n{ADD_TEXT_GATEWAY_TEXT}",
        reply_markup=after_meal_saved_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == NavCallback.MAIN_MENU)
async def nav_main_menu(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Return to the compact action menu."""
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    view = await _stats(session, settings).today_view(user.id)
    line = format_today_status_line(view)
    text = f"{line}\n\n{MAIN_MENU_TITLE}"
    await callback.message.edit_text(text, reply_markup=primary_menu_keyboard())
    await callback.answer()
