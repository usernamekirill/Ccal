from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.config import Settings
from calorie_bot.app.database.models import Meal
from calorie_bot.app.database.telegram_safe_commit import commit_db_work_before_telegram
from calorie_bot.app.domain import MealSource
from calorie_bot.app.keyboards.confirmation import after_meal_saved_keyboard
from calorie_bot.app.keyboards.meal import photo_review_keyboard, today_meals_keyboard
from calorie_bot.app.keyboards.nav_footer import append_navigation_footer
from calorie_bot.app.messages.texts import (
    MEAL_NOT_FOUND_TEXT,
    render_today_meals_text,
)
from calorie_bot.app.repositories.meal_change_log_repository import MealChangeLogRepository
from calorie_bot.app.repositories.meal_repository import MealRepository
from calorie_bot.app.repositories.profile_repository import ProfileRepository
from calorie_bot.app.repositories.stats_repository import StatsRepository
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.services.daily_stats_sync import on_meal_soft_deleted
from calorie_bot.app.services.meal_service import MealService, meal_model_to_draft
from calorie_bot.app.services.stats_service import StatsService
from calorie_bot.app.services.user_service import UserService
from calorie_bot.app.states.meal import MealStates
from calorie_bot.app.stats.formatting import format_today_status_line

router = Router(name="today")


@router.message(Command("today"))
@router.message(F.text.casefold() == "сегодня")
async def today_command(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Show today's saved meals with edit and delete controls."""
    if message.from_user is None:
        return
    user = await UserService(session).ensure_user(message.from_user)
    meals = await _today_meals(session, settings, user.id)
    text, keyboard = await _today_screen_content(session, settings, user.id, meals)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "today:list")
async def today_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Show today's saved meals from the main menu."""
    user = await UserService(session).ensure_user(callback.from_user)
    meals = await _today_meals(session, settings, user.id)
    text, keyboard = await _today_screen_content(session, settings, user.id, meals)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("today:edit:"))
async def edit_today_meal(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Load a saved meal into FSM review mode for editing."""
    user = await UserService(session).ensure_user(callback.from_user)
    meal_id = int(callback.data.rsplit(":", maxsplit=1)[1])
    meal = await MealRepository(session).get_user_meal(user.id, meal_id)
    if meal is None:
        await callback.answer(MEAL_NOT_FOUND_TEXT, show_alert=True)
        return

    calorie_service = CalorieService()
    result = calorie_service.draft_to_result(meal_model_to_draft(meal))
    await state.set_state(MealStates.photo_review)
    await state.update_data(
        photo_food_result=calorie_service.result_to_dict(result),
        photo_user_id=user.id,
        food_source=MealSource.MIXED.value,
        editing_saved_meal_id=meal.id,
    )
    await callback.message.edit_text(
        calorie_service.format_result(result),
        reply_markup=photo_review_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("today:delete:"))
async def delete_today_meal(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Soft-delete a saved meal from today's screen."""
    user = await UserService(session).ensure_user(callback.from_user)
    meal_id = int(callback.data.rsplit(":", maxsplit=1)[1])
    deleted = await MealService(
        MealRepository(session),
        MealChangeLogRepository(session),
    ).delete_saved_meal(
        user_id=user.id,
        meal_id=meal_id,
        deleted_at=datetime.now(ZoneInfo(settings.timezone)),
    )
    if deleted is None:
        await callback.answer(MEAL_NOT_FOUND_TEXT, show_alert=True)
        return
    await on_meal_soft_deleted(session, settings, user_sql_id=user.id, meal=deleted)
    await commit_db_work_before_telegram(session)
    meals = await _today_meals(session, settings, user.id)
    text, keyboard = await _today_screen_content(session, settings, user.id, meals)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


async def _today_screen_content(
    session: AsyncSession,
    settings: Settings,
    user_id: int,
    meals: list[Meal],
) -> tuple[str, object]:
    """Build status line, meal list text, and a non-dead-end keyboard."""
    stats = StatsService(
        stats_repository=StatsRepository(session),
        profile_repository=ProfileRepository(session),
        default_timezone=settings.timezone,
    )
    line = format_today_status_line(await stats.today_view(user_id))
    body = render_today_meals_text(meals)
    text = f"{line}\n\n{body}"
    if meals:
        keyboard = append_navigation_footer(today_meals_keyboard([m.id for m in meals]))
    else:
        keyboard = after_meal_saved_keyboard()
    return text, keyboard


async def _today_meals(
    session: AsyncSession,
    settings: Settings,
    user_id: int,
) -> list[Meal]:
    """Return saved meals for the configured calendar day."""
    timezone = ZoneInfo(settings.timezone)
    start_at = datetime.now(timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    end_at = start_at + timedelta(days=1)
    return await MealRepository(session).list_confirmed_between(user_id, start_at, end_at)
