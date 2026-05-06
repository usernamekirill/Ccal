"""Inline quick-picks for portion clarification; routes grams through the text-food AI (draft context)."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.ai.text_parser_service import FoodTextParserService
from calorie_bot.app.config import Settings
from calorie_bot.app.domain import MealSource
from calorie_bot.app.keyboards.confirmation import recognition_trouble_keyboard
from calorie_bot.app.keyboards.meal import (
    PORTION_CUSTOM_FREE_TEXT_HINT,
    PortionQuickPickParsed,
    parse_clarify_weight_payload,
    parse_portion_quick_pick_payload,
    photo_review_keyboard,
    portion_pick_synthetic_user_text,
)
from calorie_bot.app.messages.texts import RECOGNITION_UNCERTAIN_TEXT, TEXT_FOOD_PROCESSING_TEXT
from calorie_bot.app.security.input_validation import ensure_meal_text_length
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.services.goal_service import GoalService
from calorie_bot.app.services.onboarding_gate import food_logging_blocked_message
from calorie_bot.app.services.user_service import UserService
from calorie_bot.app.services.user_settings_service import create_user_settings_service
from calorie_bot.app.states.meal import MealStates
from calorie_bot.app.texts.settings import AI_DISABLED_HINT
from calorie_bot.app.utils.clarification_state import fsm_data_blocking_text_clarification
from calorie_bot.app.utils.clarification_ux import (
    build_blocking_clarification_ui,
    format_clarification_followup_prompt,
    resolve_draft_for_portion_quick_pick,
)
from calorie_bot.app.utils.draft_parse_context import (
    meal_parse_context,
    unresolved_clarifications_from_recognition,
)
from calorie_bot.app.utils.meal_type import infer_meal_type

router = Router(name="meal_portion_pick")
_log = logging.getLogger(__name__)


async def _send_custom_portion_free_text_hint(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(PORTION_CUSTOM_FREE_TEXT_HINT)


async def _run_portion_gram_pick_flow(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    parsed: PortionQuickPickParsed,
) -> None:
    """Apply a gram preset via text-food parser + current draft (photo or text clarification)."""
    if callback.from_user is None or callback.message is None:
        return

    user_row = await UserService(session).ensure_user(callback.from_user)
    blocked = food_logging_blocked_message(user_row)
    if blocked:
        await callback.answer(blocked, show_alert=True)
        return
    settings_svc = create_user_settings_service(session, GoalService())
    if not await settings_svc.is_ai_analysis_enabled(user_row.id):
        await callback.answer(AI_DISABLED_HINT, show_alert=True)
        return

    data = await state.get_data()
    st = await state.get_state()
    mode, draft_dict = resolve_draft_for_portion_quick_pick(data, st)
    if not mode or not draft_dict:
        await callback.answer(
            "Сначала отправь описание еды — черновик не найден.",
            show_alert=True,
        )
        return

    calorie_service = CalorieService()
    pending_fr = calorie_service.result_from_dict(draft_dict)
    try:
        user_text = portion_pick_synthetic_user_text(pending_fr, parsed).strip()
    except ValueError:
        await callback.answer("Черновик устарел — отправьте приём пищи заново.", show_alert=True)
        return

    ensure_meal_text_length(user_text, settings.max_meal_text_chars)
    await callback.answer()

    _dmt = data.get("default_meal_type")
    default_meal_type = (
        str(_dmt).strip()
        if _dmt is not None and str(_dmt).strip()
        else infer_meal_type(datetime.now(ZoneInfo(settings.timezone))).value
    )
    unresolved = unresolved_clarifications_from_recognition(pending_fr)

    if mode == "photo":
        await callback.message.answer(TEXT_FOOD_PROCESSING_TEXT)
        try:
            updated = await FoodTextParserService(settings).parse_food_text(
                user_text.strip(),
                default_meal_type=default_meal_type,
                context=meal_parse_context(
                    data,
                    current_draft=pending_fr,
                    unresolved_clarifications=unresolved,
                ),
            )
        except Exception:
            _log.exception("portion_pick_photo_parse_failed")
            await callback.message.answer(
                RECOGNITION_UNCERTAIN_TEXT,
                reply_markup=recognition_trouble_keyboard(),
            )
            return
        updated = calorie_service.with_default_meal_type(
            updated,
            infer_meal_type(datetime.now(ZoneInfo(settings.timezone))),
        )
        try:
            updated = await calorie_service.enrich_after_text_processing(
                updated,
                user_text.strip(),
                session,
                settings,
            )
        except Exception:
            _log.exception("portion_pick_photo_enrich_failed")
            await callback.message.answer(
                RECOGNITION_UNCERTAIN_TEXT,
                reply_markup=recognition_trouble_keyboard(),
            )
            return
        updated = calorie_service.apply_clarification_guards(updated)
        if calorie_service.requires_blocking_clarification(updated):
            clar_body, clar_kb, updated = await build_blocking_clarification_ui(
                calorie_service=calorie_service,
                result=updated,
                settings=settings,
            )
            await state.update_data(photo_food_result=calorie_service.result_to_dict(updated))
            await callback.message.answer(clar_body, reply_markup=clar_kb)
            return
        if not updated.items:
            await callback.message.answer(
                RECOGNITION_UNCERTAIN_TEXT,
                reply_markup=recognition_trouble_keyboard(),
            )
            return
        await state.set_state(MealStates.photo_review)
        await state.update_data(
            photo_food_result=calorie_service.result_to_dict(updated),
            clarification_mode=None,
            pending_text_food=None,
            pending_food_result_draft=None,
            pending_food=None,
            food_source=data.get("food_source", MealSource.PHOTO.value),
        )
        await callback.message.answer(
            calorie_service.format_result(updated),
            reply_markup=photo_review_keyboard(),
        )
        return

    await callback.message.answer(TEXT_FOOD_PROCESSING_TEXT)
    try:
        result = await FoodTextParserService(settings).parse_food_text(
            user_text.strip(),
            default_meal_type=default_meal_type,
            context=meal_parse_context(
                data,
                current_draft=pending_fr,
                unresolved_clarifications=unresolved,
            ),
        )
    except Exception:
        _log.exception("portion_pick_text_draft_parse_failed")
        await callback.message.answer(
            RECOGNITION_UNCERTAIN_TEXT,
            reply_markup=recognition_trouble_keyboard(),
        )
        return
    result = calorie_service.with_default_meal_type(
        result,
        infer_meal_type(datetime.now(ZoneInfo(settings.timezone))),
    )
    try:
        result = await calorie_service.enrich_after_text_processing(
            result,
            user_text.strip(),
            session,
            settings,
        )
    except Exception:
        _log.exception("portion_pick_text_draft_enrich_failed")
        await callback.message.answer(
            RECOGNITION_UNCERTAIN_TEXT,
            reply_markup=recognition_trouble_keyboard(),
        )
        return
    result = calorie_service.apply_clarification_guards(result)
    if calorie_service.requires_blocking_clarification(result):
        clar_body, clar_kb, result = await build_blocking_clarification_ui(
            calorie_service=calorie_service,
            result=result,
            settings=settings,
        )
        next_state = (
            MealStates.waiting_for_weight
            if calorie_service.is_portion_weight_blocking_only(result)
            else MealStates.waiting_for_correction
        )
        await state.set_state(next_state)
        await state.update_data(
            **fsm_data_blocking_text_clarification(
                calorie_service,
                result,
                pending_text=str(data.get("pending_text_food") or user_text),
                default_meal_type=default_meal_type,
            ),
        )
        await callback.message.answer(clar_body, reply_markup=clar_kb)
        return
    if not result.items:
        if result.needs_clarification and result.clarification_question:
            await state.set_state(MealStates.waiting_for_correction)
            await state.update_data(
                pending_text_food=str(data.get("pending_text_food") or ""),
                default_meal_type=default_meal_type,
                clarification_mode=None,
                pending_food_result_draft=None,
                pending_food=None,
            )
            await callback.message.answer(format_clarification_followup_prompt(result))
        else:
            await callback.message.answer(
                RECOGNITION_UNCERTAIN_TEXT,
                reply_markup=recognition_trouble_keyboard(),
            )
        return
    await state.set_state(MealStates.photo_review)
    await state.update_data(
        photo_food_result=calorie_service.result_to_dict(result),
        food_source=data.get("food_source", MealSource.TEXT_AI.value),
        pending_text_food=None,
        pending_food_result_draft=None,
        pending_food=None,
        clarification_mode=None,
    )
    await callback.message.answer(
        calorie_service.format_result(result),
        reply_markup=photo_review_keyboard(),
    )


@router.callback_query(F.data.startswith("mpt:"))
async def handle_portion_quick_pick(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Legacy ``mpt:`` quick-picks (single-product presets)."""
    if callback.data is None or callback.from_user is None:
        return
    raw = callback.data.split(":", 1)[1]
    try:
        parsed = parse_portion_quick_pick_payload(raw)
    except ValueError:
        await callback.answer("Не удалось разобрать кнопку. Попробуйте ещё раз.", show_alert=True)
        return
    if parsed.kind == "custom":
        await _send_custom_portion_free_text_hint(callback)
        return
    await _run_portion_gram_pick_flow(callback, state, session, settings, parsed)


@router.callback_query(F.data.startswith("clarify_weight:"))
async def handle_clarify_weight_pick(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Item-scoped gram presets (composite dishes)."""
    if callback.data is None or callback.from_user is None:
        return
    raw = callback.data.split(":", 1)[1]
    try:
        parsed = parse_clarify_weight_payload(raw)
    except ValueError:
        await callback.answer("Не удалось разобрать кнопку. Попробуйте ещё раз.", show_alert=True)
        return
    if parsed.kind == "custom":
        await _send_custom_portion_free_text_hint(callback)
        return
    await _run_portion_gram_pick_flow(callback, state, session, settings, parsed)
