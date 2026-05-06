"""Tests for conversational clarification UX helpers."""

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.states.meal import MealStates
from calorie_bot.app.utils.clarification_ux import (
    format_blocking_clarification_message,
    format_clarification_followup_prompt,
    resolve_draft_for_portion_quick_pick,
)
from calorie_bot.app.utils.food_emoji import food_line_emoji


def _item(name: str, *, grams: float | None = None) -> FoodItemRecognition:
    return FoodItemRecognition.model_validate(
        {
            "name": name,
            "portion_description": "порция",
            "estimated_grams": grams,
            "calories": 0,
        }
    )


def test_food_line_emoji_sharlotka() -> None:
    """Dessert names get a cake emoji."""
    assert "🍰" == food_line_emoji("кусок шарлотки")


def test_format_blocking_portion_only_includes_quick_pick_keyboard() -> None:
    """Single-item weight-only blocking clarification gets inline presets."""
    svc = CalorieService()
    result = FoodRecognitionResult(
        items=[_item("Гречка", grams=None)],
        total_calories=0,
        overall_confidence=0.8,
        comment="test",
        needs_clarification=True,
        clarification_question="Сколько грамм?",
    )
    body, kb = format_blocking_clarification_message(svc, result)
    assert "Гречка" in body
    assert "Сколько примерно было?" in body
    assert kb is not None
    assert any("mpt:150" in str(btn.callback_data) for row in kb.inline_keyboard for btn in row)


def test_format_blocking_non_portion_has_no_keyboard() -> None:
    """Multi-item blocking questions stay text-only."""
    svc = CalorieService()
    result = FoodRecognitionResult(
        items=[
            _item("Сыр", grams=None),
            _item("Хлеб", grams=None),
        ],
        total_calories=0,
        overall_confidence=0.8,
        comment="test",
        needs_clarification=True,
        clarification_question="Какой сыр?",
    )
    body, kb = format_blocking_clarification_message(svc, result)
    assert "Какой сыр?" in body
    assert kb is None


def test_resolve_draft_for_portion_quick_pick_text_weight_state() -> None:
    """waiting_for_weight uses pending_food_result_draft."""
    draft = {"items": [], "total_calories": 0, "overall_confidence": 0.8, "comment": "x"}
    mode, d = resolve_draft_for_portion_quick_pick(
        {"pending_food_result_draft": draft},
        MealStates.waiting_for_weight.state,
    )
    assert mode == "text_draft"
    assert d == draft


def test_format_clarification_followup_prompt() -> None:
    """Free-form follow-up wraps model question."""
    result = FoodRecognitionResult(
        items=[],
        total_calories=0,
        overall_confidence=0.5,
        comment="c",
        needs_clarification=True,
        clarification_question="Какой соус?",
    )
    text = format_clarification_followup_prompt(result)
    assert "Какой соус?" in text
