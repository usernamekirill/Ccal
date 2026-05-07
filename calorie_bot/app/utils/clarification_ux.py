"""Conversational clarification copy, FSM helpers, and AI-orchestrated blocking UI."""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardMarkup

from calorie_bot.app.ai.clarification_orchestrator import (
    build_llm_context,
    fallback_clarification_body,
    missing_weight_portion_actions,
    multi_item_missing_weight_clarification_body,
)
from calorie_bot.app.ai.clarification_reply_service import ClarificationReplyService
from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.config import Settings
from calorie_bot.app.keyboards.meal import contextual_portion_keyboard
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.states.meal import MealStates


async def build_blocking_clarification_template_only(
    *,
    calorie_service: CalorieService,
    result: FoodRecognitionResult,
    settings: Settings,
) -> tuple[str, InlineKeyboardMarkup | None, FoodRecognitionResult]:
    """Blocking clarification using local copy + presets only (no meal-clarification LLM call)."""
    _ = settings
    ctx = build_llm_context(result, calorie_service)
    body = multi_item_missing_weight_clarification_body(ctx)
    if not body:
        body = fallback_clarification_body(ctx)
    actions = missing_weight_portion_actions(result) if ctx.primary_issue == "missing_weight" else []
    single_item = len(result.items) == 1
    kb = (
        contextual_portion_keyboard(
            actions,
            single_ingredient_clarification=single_item,
        )
        if actions
        else None
    )
    merged = result.model_copy(
        update={
            "clarification_question": body,
            "needs_clarification": True,
        }
    )
    return (body, kb, merged)


async def build_blocking_clarification_ui(
    *,
    calorie_service: CalorieService,
    result: FoodRecognitionResult,
    settings: Settings,
) -> tuple[str, InlineKeyboardMarkup | None, FoodRecognitionResult]:
    """One conversational clarification turn (AI + contextual quick actions, single stored question)."""
    ctx = build_llm_context(result, calorie_service)
    return await ClarificationReplyService(settings).build_reply_for_result(result, ctx)


def format_clarification_followup_prompt(result: FoodRecognitionResult) -> str:
    """Short prompt when waiting for a free-form clarification answer (no solid draft lines yet)."""
    q = (result.clarification_question or "").strip()
    if not q:
        return "Напиши ответ одним сообщением — разберёмся ✍️"
    return f"Уточним так 👇\n\n{q}"


def resolve_draft_for_portion_quick_pick(
    data: dict[str, Any],
    state: str | None,
) -> tuple[str | None, dict[str, Any] | None]:
    """Return (mode, draft_dict) for applying a grams quick-pick via AI. mode is ``photo`` or ``text_draft``."""
    if state == MealStates.waiting_for_weight.state:
        d = data.get("pending_food_result_draft")
        if isinstance(d, dict) and d:
            return ("text_draft", d)
        return (None, None)
    if state == MealStates.waiting_for_correction.state:
        if data.get("clarification_mode") == "photo" and data.get("photo_food_result"):
            d = data["photo_food_result"]
            if isinstance(d, dict) and d:
                return ("photo", d)
        if data.get("clarification_mode") == "text_draft" and data.get("pending_food_result_draft"):
            d = data["pending_food_result_draft"]
            if isinstance(d, dict) and d:
                return ("text_draft", d)
    return (None, None)
