"""Conversational clarification copy and FSM helpers for meal flows."""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardMarkup

from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.keyboards.meal import portion_quick_pick_keyboard
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.states.meal import MealStates
from calorie_bot.app.utils.food_emoji import food_line_emoji


def format_blocking_clarification_message(
    calorie_service: CalorieService,
    result: FoodRecognitionResult,
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Build human-friendly blocking clarification text and optional portion keyboard."""
    q = (result.clarification_question or "").strip()
    if calorie_service.is_portion_weight_blocking_only(result):
        it = result.items[0]
        title = (it.name or "Блюдо").strip()
        emoji = food_line_emoji(title)
        lines = [
            f"{emoji} {title}",
            "",
            "Сколько примерно было?",
            "",
            "Можно выбрать вариант ниже или написать свой вес ✍️",
        ]
        return ("\n".join(lines), portion_quick_pick_keyboard())
    lead = "Давай уточним — так посчитаю точнее 👇"
    body = f"{lead}\n\n{q}" if q else lead
    return (body, None)


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
