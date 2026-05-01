from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.ai.text_parser_service import FoodTextParserService
from calorie_bot.app.config import Settings
from calorie_bot.app.domain import MealSource
from calorie_bot.app.keyboards.meal import photo_review_keyboard
from calorie_bot.app.messages.texts import (
    TEXT_FOOD_CLARIFICATION_PREFIX,
    TEXT_FOOD_PROCESSING_TEXT,
)
from calorie_bot.app.security.input_validation import ensure_meal_text_length
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.services.goal_service import GoalService
from calorie_bot.app.services.onboarding_gate import food_logging_blocked_message
from calorie_bot.app.services.user_service import UserService
from calorie_bot.app.services.user_settings_service import create_user_settings_service
from calorie_bot.app.states.meal import MealStates
from calorie_bot.app.states.settings import SettingsStates
from calorie_bot.app.texts.settings import AI_DISABLED_HINT
from calorie_bot.app.utils.meal_type import infer_meal_type

router = Router(name="text_food")


@router.message(F.text)
async def handle_text_food(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Parse a text meal into a confirmable FSM draft."""
    if message.from_user is None or message.text is None or message.text.startswith("/"):
        return
    if await state.get_state() == MealStates.photo_editing.state:
        return
    if await state.get_state() == SettingsStates.entering_calorie_goal.state:
        return

    user = await UserService(session).ensure_user(message.from_user)
    blocked = food_logging_blocked_message(user)
    if blocked:
        await message.answer(blocked)
        return
    settings_svc = create_user_settings_service(session, GoalService())
    if not await settings_svc.is_ai_analysis_enabled(user.id):
        await message.answer(AI_DISABLED_HINT)
        return
    ensure_meal_text_length(message.text, settings.max_meal_text_chars)
    timezone = ZoneInfo(settings.timezone)
    default_meal_type = infer_meal_type(datetime.now(timezone))
    await message.answer(TEXT_FOOD_PROCESSING_TEXT)

    result = await FoodTextParserService(settings).parse_food_text(
        message.text,
        default_meal_type=default_meal_type.value,
    )

    if result.needs_clarification and result.clarification_question:
        await state.set_state(MealStates.waiting_for_correction)
        await state.update_data(
            pending_text_food=message.text,
            default_meal_type=default_meal_type.value,
        )
        await message.answer(f"{TEXT_FOOD_CLARIFICATION_PREFIX} {result.clarification_question}")
        return

    calorie_service = CalorieService()
    result = calorie_service.with_default_meal_type(result, default_meal_type)
    await state.set_state(MealStates.photo_review)
    await state.update_data(
        photo_food_result=calorie_service.result_to_dict(result),
        food_source=MealSource.TEXT.value,
    )
    await message.answer(
        calorie_service.format_result(result),
        reply_markup=photo_review_keyboard(),
    )


@router.message(MealStates.waiting_for_correction)
async def handle_text_food_clarification(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Parse text meal again after one clarification answer."""
    if message.from_user is None:
        return
    user_row = await UserService(session).ensure_user(message.from_user)
    blocked = food_logging_blocked_message(user_row)
    if blocked:
        await message.answer(blocked)
        return
    settings_svc = create_user_settings_service(session, GoalService())
    if not await settings_svc.is_ai_analysis_enabled(user_row.id):
        await message.answer(AI_DISABLED_HINT)
        return
    data = await state.get_data()
    original_text = str(data.get("pending_text_food", ""))
    default_meal_type = str(data.get("default_meal_type", infer_meal_type(datetime.now()).value))
    combined_text = f"{original_text}. Уточнение: {message.text or ''}"
    ensure_meal_text_length(combined_text, settings.max_meal_text_chars)

    result = await FoodTextParserService(settings).parse_food_text(
        combined_text,
        default_meal_type=default_meal_type,
    )

    calorie_service = CalorieService()
    result = calorie_service.with_default_meal_type(result, infer_meal_type(datetime.now()))
    await state.set_state(MealStates.photo_review)
    await state.update_data(
        photo_food_result=calorie_service.result_to_dict(result),
        food_source=MealSource.TEXT.value,
        pending_text_food=None,
    )
    await message.answer(
        calorie_service.format_result(result),
        reply_markup=photo_review_keyboard(),
    )
