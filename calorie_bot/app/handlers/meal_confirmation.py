from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.config import Settings
from calorie_bot.app.database.telegram_safe_commit import commit_db_work_before_telegram
from calorie_bot.app.keyboards.confirmation import draft_cancelled_keyboard
from calorie_bot.app.keyboards.nav_footer import navigation_footer_keyboard
from calorie_bot.app.messages.ux_flow import MEAL_CANCEL_FOLLOWUP
from calorie_bot.app.post_action_message import send_post_action_message
from calorie_bot.app.repositories.meal_repository import MealRepository
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.services.daily_stats_sync import on_meal_confirmed
from calorie_bot.app.services.meal_service import MealService, meal_model_to_draft
from calorie_bot.app.services.motivation_service import create_motivation_service
from calorie_bot.app.services.user_service import UserService

router = Router(name="meal_confirmation")


@router.callback_query(F.data == "meal:confirm")
async def confirm_meal(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Confirm the latest meal draft and show day statistics."""
    user = await UserService(session).ensure_user(callback.from_user)
    meal = await MealService(MealRepository(session)).confirm_latest_draft(user.id)
    if meal is None:
        await callback.answer(MEAL_NOT_FOUND_TEXT, show_alert=True)
        return

    calorie = CalorieService()
    brief = calorie.format_saved_meal_brief(calorie.draft_to_result(meal_model_to_draft(meal)))
    await on_meal_confirmed(session, settings, user_sql_id=user.id, meal=meal)
    await commit_db_work_before_telegram(session)
    await send_post_action_message(
        callback.message,
        session=session,
        settings=settings,
        user_id=user.id,
        meal_brief_text=brief,
        edit_in_place=True,
    )
    motivation = await create_motivation_service(session, settings).maybe_emit(
        user.id,
        "meal_save",
        meal_was_new=True,
    )
    if motivation:
        await callback.message.answer(motivation, reply_markup=navigation_footer_keyboard())
    await callback.answer()


@router.callback_query(F.data == "meal:cancel")
async def cancel_meal(callback: CallbackQuery, session: AsyncSession) -> None:
    """Cancel the latest meal draft."""
    user = await UserService(session).ensure_user(callback.from_user)
    meal = await MealService(MealRepository(session)).cancel_latest_draft(user.id)
    if meal is None:
        await callback.answer(MEAL_NOT_FOUND_TEXT, show_alert=True)
        return
    await callback.message.edit_text(MEAL_CANCEL_FOLLOWUP, reply_markup=draft_cancelled_keyboard())
    await callback.answer()


@router.callback_query(F.data == "meal:edit")
async def edit_meal(callback: CallbackQuery) -> None:
    """Point to native corrections on the current draft."""
    await callback.answer()
    await callback.message.answer(
        "Напишите правку одним сообщением в чат или отправьте голосовое — я обновлю черновик.\n"
        "Примеры: «кулич 50 г», «убери второй продукт», «добавь кофе 200 г, 10 ккал».",
        reply_markup=draft_cancelled_keyboard(),
    )
