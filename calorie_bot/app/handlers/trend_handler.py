"""Handlers for rolling nutrition trends (7 / 14 / 30 days)."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.config import Settings
from calorie_bot.app.keyboards.nav_footer import append_navigation_footer
from calorie_bot.app.keyboards.trends import trend_window_keyboard
from calorie_bot.app.repositories.profile_repository import ProfileRepository
from calorie_bot.app.repositories.stats_repository import StatsRepository
from calorie_bot.app.services.stats_service import StatsService
from calorie_bot.app.services.trend_service import TrendService
from calorie_bot.app.services.user_service import UserService
from calorie_bot.app.stats.formatting import format_today_status_line
from calorie_bot.app.trends.formatting import format_trend_report

router = Router(name="trends")

_VALID = frozenset({7, 14, 30})


def _stats_service(session: AsyncSession, settings: Settings) -> StatsService:
    """Daily snapshot for status line."""
    return StatsService(
        stats_repository=StatsRepository(session),
        profile_repository=ProfileRepository(session),
        default_timezone=settings.timezone,
    )


def _trend_service(session: AsyncSession, settings: Settings) -> TrendService:
    """Construct ``TrendService`` for the active DB session."""
    return TrendService(
        stats_repository=StatsRepository(session),
        profile_repository=ProfileRepository(session),
        default_timezone=settings.timezone,
    )


@router.message(Command("trends"))
async def trends_command(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Show a 7-day trend by default and window switcher."""
    if message.from_user is None:
        return
    user = await UserService(session).ensure_user(message.from_user)
    report = await _trend_service(session, settings).build_report(user.id, 7)
    text = format_trend_report(report)
    line = format_today_status_line(await _stats_service(session, settings).today_view(user.id))
    await message.answer(
        f"{line}\n\nТренд за 7 дн.\n\n{text}",
        reply_markup=append_navigation_footer(trend_window_keyboard(active_days=7)),
    )


@router.callback_query(F.data.startswith("trend:"))
async def trends_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Render a trend report for 7, 14, or 30 days."""
    raw = callback.data.split(":", maxsplit=1)[1]
    try:
        window_days = int(raw)
    except ValueError:
        await callback.answer("Неизвестный период.", show_alert=True)
        return

    if window_days not in _VALID:
        await callback.answer("Доступны только 7, 14 или 30 дней.", show_alert=True)
        return

    user = await UserService(session).ensure_user(callback.from_user)
    report = await _trend_service(session, settings).build_report(user.id, window_days)
    text = format_trend_report(report)
    title = f"Тренд за {window_days} дн."
    line = format_today_status_line(await _stats_service(session, settings).today_view(user.id))
    await callback.message.edit_text(
        f"{line}\n\n{title}\n\n{text}",
        reply_markup=append_navigation_footer(trend_window_keyboard(active_days=window_days)),
    )
    await callback.answer()
