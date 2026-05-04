import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.ai.text_parser_service import FoodTextParserService
from calorie_bot.app.config import Settings
from calorie_bot.app.domain import MealSource
from calorie_bot.app.keyboards.confirmation import recognition_trouble_keyboard
from calorie_bot.app.keyboards.meal import photo_review_keyboard
from calorie_bot.app.messages.texts import (
    RECOGNITION_UNCERTAIN_TEXT,
    TEXT_FOOD_CLARIFICATION_PREFIX,
    TEXT_FOOD_PROCESSING_TEXT,
)
from calorie_bot.app.security.input_validation import ensure_meal_text_length
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.services.edit_interpreter_service import apply_instruction_to_food_result
from calorie_bot.app.services.goal_service import GoalService
from calorie_bot.app.services.onboarding_gate import food_logging_blocked_message
from calorie_bot.app.services.user_service import UserService
from calorie_bot.app.services.user_settings_service import create_user_settings_service
from calorie_bot.app.states.meal import MealStates
from calorie_bot.app.states.settings import SettingsStates
from calorie_bot.app.texts.settings import AI_DISABLED_HINT
from calorie_bot.app.utils.clarification_state import fsm_data_blocking_text_clarification
from calorie_bot.app.utils.meal_type import infer_meal_type

router = Router(name="text_food")
_log = logging.getLogger(__name__)


@router.message(MealStates.waiting_for_correction, F.text)
async def handle_text_food_clarification(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Parse text meal again after one clarification answer."""
    if message.from_user is None or message.text is None or message.text.startswith("/"):
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
    calorie_service = CalorieService()

    if data.get("clarification_mode") == "photo" and data.get("photo_food_result"):
        current = calorie_service.result_from_dict(data["photo_food_result"])
        ensure_meal_text_length(message.text, settings.max_meal_text_chars)
        try:
            updated = await apply_instruction_to_food_result(
                settings,
                message.text.strip(),
                current,
                session=session,
            )
        except Exception:
            await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
            return
        updated = calorie_service.apply_clarification_guards(updated)
        if calorie_service.requires_blocking_clarification(updated):
            await state.update_data(photo_food_result=calorie_service.result_to_dict(updated))
            await message.answer(f"{TEXT_FOOD_CLARIFICATION_PREFIX}\n{updated.clarification_question}")
            return
        await state.set_state(MealStates.photo_review)
        await state.update_data(
            photo_food_result=calorie_service.result_to_dict(updated),
            clarification_mode=None,
            pending_text_food=None,
            pending_food_result_draft=None,
            food_source=data.get("food_source", MealSource.TEXT.value),
        )
        reply = calorie_service.format_result(updated)
        if updated.needs_clarification and updated.clarification_question:
            reply = f"{reply}\n\n⚠️ {updated.clarification_question}"
        await message.answer(reply, reply_markup=photo_review_keyboard())
        return

    if data.get("clarification_mode") == "text_draft" and data.get("pending_food_result_draft"):
        current = calorie_service.result_from_dict(data["pending_food_result_draft"])
        ensure_meal_text_length(message.text, settings.max_meal_text_chars)
        try:
            updated = await apply_instruction_to_food_result(
                settings,
                message.text.strip(),
                current,
                session=session,
            )
        except Exception:
            await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
            return
        updated = calorie_service.apply_clarification_guards(updated)
        if calorie_service.requires_blocking_clarification(updated):
            await state.update_data(pending_food_result_draft=calorie_service.result_to_dict(updated))
            await message.answer(f"{TEXT_FOOD_CLARIFICATION_PREFIX}\n{updated.clarification_question}")
            return
        if not updated.items:
            await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
            return
        await state.set_state(MealStates.photo_review)
        await state.update_data(
            photo_food_result=calorie_service.result_to_dict(updated),
            pending_food_result_draft=None,
            clarification_mode=None,
            pending_text_food=None,
            food_source=MealSource.TEXT.value,
        )
        reply = calorie_service.format_result(updated)
        if updated.needs_clarification and updated.clarification_question:
            reply = f"{reply}\n\n⚠️ {updated.clarification_question}"
        await message.answer(reply, reply_markup=photo_review_keyboard())
        return

    original_text = str(data.get("pending_text_food", ""))
    default_meal_type = str(data.get("default_meal_type", infer_meal_type(datetime.now()).value))
    combined_text = f"{original_text}. Уточнение: {message.text or ''}"
    ensure_meal_text_length(combined_text, settings.max_meal_text_chars)

    try:
        result = await FoodTextParserService(settings).parse_food_text(
            combined_text,
            default_meal_type=default_meal_type,
        )
    except Exception:
        _log.exception("text_meal_clarification_parse_failed")
        await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
        return

    result = calorie_service.with_default_meal_type(result, infer_meal_type(datetime.now()))
    result = calorie_service.apply_user_text_gram_priority(combined_text, result)
    try:
        result = await calorie_service.enrich_after_text_processing(
            result, combined_text, session, settings
        )
    except Exception:
        _log.exception("text_meal_clarification_enrich_failed")
        await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
        return

    result = calorie_service.apply_clarification_guards(result)
    if calorie_service.requires_blocking_clarification(result):
        await state.set_state(MealStates.waiting_for_correction)
        await state.update_data(
            **fsm_data_blocking_text_clarification(
                calorie_service,
                result,
                pending_text=combined_text,
                default_meal_type=default_meal_type,
            ),
        )
        await message.answer(f"{TEXT_FOOD_CLARIFICATION_PREFIX}\n{result.clarification_question}")
        return

    if not result.items:
        if result.needs_clarification and result.clarification_question:
            await state.set_state(MealStates.waiting_for_correction)
            await state.update_data(
                pending_text_food=original_text,
                default_meal_type=default_meal_type,
                clarification_mode=None,
                pending_food_result_draft=None,
            )
            await message.answer(f"{TEXT_FOOD_CLARIFICATION_PREFIX} {result.clarification_question}")
        else:
            await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
        return

    await state.set_state(MealStates.photo_review)
    await state.update_data(
        photo_food_result=calorie_service.result_to_dict(result),
        food_source=MealSource.TEXT.value,
        pending_text_food=None,
        pending_food_result_draft=None,
        clarification_mode=None,
    )
    reply = calorie_service.format_result(result)
    if result.needs_clarification and result.clarification_question:
        reply = f"{reply}\n\n⚠️ {result.clarification_question}"
    await message.answer(reply, reply_markup=photo_review_keyboard())


@router.message(MealStates.photo_review, F.text)
async def handle_draft_text_correction(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """While a meal draft is visible, treat a new text line as an edit, not a new meal."""
    if message.from_user is None or message.text is None or message.text.startswith("/"):
        return
    data = await state.get_data()
    if not data.get("photo_food_result"):
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

    calorie_service = CalorieService()
    current = calorie_service.result_from_dict(data["photo_food_result"])
    ensure_meal_text_length(message.text, settings.max_meal_text_chars)

    try:
        updated = await apply_instruction_to_food_result(
            settings,
            message.text,
            current,
            session=session,
        )
    except Exception:
        await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
        return

    updated = calorie_service.apply_clarification_guards(updated)
    if calorie_service.requires_blocking_clarification(updated):
        await state.set_state(MealStates.waiting_for_correction)
        await state.update_data(
            photo_food_result=calorie_service.result_to_dict(updated),
            clarification_mode="photo",
        )
        await message.answer(f"{TEXT_FOOD_CLARIFICATION_PREFIX}\n{updated.clarification_question}")
        return

    await state.update_data(
        photo_food_result=calorie_service.result_to_dict(updated),
        food_source=data.get("food_source", MealSource.TEXT.value),
    )
    reply = calorie_service.format_result(updated)
    if updated.needs_clarification and updated.clarification_question:
        reply = f"{reply}\n\n⚠️ {updated.clarification_question}"
    await message.answer(reply, reply_markup=photo_review_keyboard())


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

    try:
        result = await FoodTextParserService(settings).parse_food_text(
            message.text,
            default_meal_type=default_meal_type.value,
        )
    except Exception:
        _log.exception("text_meal_parse_failed")
        await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
        return

    calorie_service = CalorieService()
    result = calorie_service.with_default_meal_type(result, default_meal_type)
    result = calorie_service.apply_user_text_gram_priority(message.text, result)
    try:
        result = await calorie_service.enrich_after_text_processing(
            result, message.text, session, settings
        )
    except Exception:
        _log.exception("text_meal_enrich_failed")
        await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
        return

    result = calorie_service.apply_clarification_guards(result)
    if calorie_service.requires_blocking_clarification(result):
        await state.set_state(MealStates.waiting_for_correction)
        await state.update_data(
            **fsm_data_blocking_text_clarification(
                calorie_service,
                result,
                pending_text=message.text,
                default_meal_type=default_meal_type.value,
            ),
        )
        await message.answer(f"{TEXT_FOOD_CLARIFICATION_PREFIX}\n{result.clarification_question}")
        return

    if not result.items:
        if result.needs_clarification and result.clarification_question:
            await state.set_state(MealStates.waiting_for_correction)
            await state.update_data(
                pending_text_food=message.text,
                default_meal_type=default_meal_type.value,
                clarification_mode=None,
                pending_food_result_draft=None,
            )
            await message.answer(f"{TEXT_FOOD_CLARIFICATION_PREFIX} {result.clarification_question}")
        else:
            await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
        return

    await state.set_state(MealStates.photo_review)
    await state.update_data(
        photo_food_result=calorie_service.result_to_dict(result),
        food_source=MealSource.TEXT.value,
        pending_text_food=None,
        pending_food_result_draft=None,
        clarification_mode=None,
    )
    reply = calorie_service.format_result(result)
    if result.needs_clarification and result.clarification_question:
        reply = f"{reply}\n\n⚠️ {result.clarification_question}"
    await message.answer(reply, reply_markup=photo_review_keyboard())
