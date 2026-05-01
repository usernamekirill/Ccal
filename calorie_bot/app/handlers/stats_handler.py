"""Telegram handlers for nutrition statistics (day / week / month)."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.config import Settings
from calorie_bot.app.domain import StatsPeriod
from calorie_bot.app.keyboards.nav_footer import (
    append_navigation_footer,
    navigation_footer_keyboard,
)
from calorie_bot.app.keyboards.stats import stats_period_keyboard
from calorie_bot.app.repositories.profile_repository import ProfileRepository
from calorie_bot.app.repositories.stats_repository import StatsRepository
from calorie_bot.app.services.motivation_service import create_motivation_service
from calorie_bot.app.services.stats_service import StatsService
from calorie_bot.app.services.user_service import UserService
from calorie_bot.app.stats.formatting import (
    format_month_stats,
    format_today_stats,
    format_today_status_line,
    format_week_stats,
)

router = Router(name="stats")

PERIOD_TITLE: dict[StatsPeriod, str] = {
    StatsPeriod.DAY: "Сегодня",
    StatsPeriod.WEEK: "Неделя",
    StatsPeriod.MONTH: "Месяц",
}


def _stats_service(session: AsyncSession, settings: Settings) -> StatsService:
    """Build a ``StatsService`` with repositories for the current request."""
    return StatsService(
        stats_repository=StatsRepository(session),
        profile_repository=ProfileRepository(session),
        default_timezone=settings.timezone,
    )


@router.message(Command("stats"))
async def stats_command(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Offer period buttons for statistics."""
    if message.from_user is None:
        return
    user = await UserService(session).ensure_user(message.from_user)
    service = _stats_service(session, settings)
    line = format_today_status_line(await service.today_view(user.id))
    await message.answer(
        f"{line}\n\nВыбери период статистики:",
        reply_markup=append_navigation_footer(stats_period_keyboard()),
    )


@router.callback_query(F.data.startswith("stats:"))
async def stats_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Render rich statistics for the chosen period."""
    period = StatsPeriod(callback.data.split(":", maxsplit=1)[1])
    user = await UserService(session).ensure_user(callback.from_user)
    service = _stats_service(session, settings)
    today_line = format_today_status_line(await service.today_view(user.id))

    if period == StatsPeriod.DAY:
        view = await service.today_view(user.id)
        text = format_today_stats(view)
    elif period == StatsPeriod.WEEK:
        view = await service.week_view(user.id)
        text = format_week_stats(view)
    else:
        view = await service.month_view(user.id)
        text = format_month_stats(view)

    title = PERIOD_TITLE[period]
    await callback.message.edit_text(
        f"{today_line}\n\n{title}\n\n{text}",
        reply_markup=append_navigation_footer(stats_period_keyboard(active=period)),
    )
    motivation = await create_motivation_service(session, settings).maybe_emit(
        user.id,
        "stats",
    )
    if motivation:
        await callback.message.answer(motivation, reply_markup=navigation_footer_keyboard())
    await callback.answer()
