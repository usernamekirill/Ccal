"""Tests for conversational clarification UX helpers."""

import pytest
from pydantic import SecretStr

from calorie_bot.app.ai.clarification_reply_service import (
    ClarificationReplyPayload,
    ClarificationReplyService,
    QuickActionSpec,
)
from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.config import Settings
from calorie_bot.app.domain import GramsSource
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.states.meal import MealStates
from calorie_bot.app.utils.clarification_ux import (
    build_blocking_clarification_ui,
    format_clarification_followup_prompt,
    resolve_draft_for_portion_quick_pick,
)
from calorie_bot.app.utils.food_emoji import food_line_emoji


def _settings_offline() -> Settings:
    return Settings(
        telegram_bot_token=SecretStr("x"),
        openai_api_key=SecretStr(""),
        database_url="sqlite+aiosqlite:///:memory:",
    )


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


@pytest.mark.asyncio
async def test_build_blocking_portion_only_includes_quick_pick_keyboard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Single-item weight-only blocking clarification gets inline presets."""
    svc = CalorieService()
    base = FoodRecognitionResult(
        items=[_item("Гречка", grams=None)],
        total_calories=0,
        overall_confidence=0.8,
        comment="test",
        needs_clarification=True,
    )
    result = svc.validate_food_result(base)
    result = svc.apply_clarification_guards(result)

    async def fake_card(self, ctx):
        return (
            "🥣 Гречка\n\nСколько примерно было?",
            ClarificationReplyPayload(
                primary_issue="missing_weight",
                message="🥣 Гречка\n\nСколько примерно было?",
                quick_actions=[
                    QuickActionSpec(grams=150, label="150 г"),
                    QuickActionSpec(grams=200, label="200 г"),
                ],
                expects_input_type="grams",
            ),
        )

    monkeypatch.setattr(ClarificationReplyService, "generate_card", fake_card)
    body, kb, merged = await build_blocking_clarification_ui(
        calorie_service=svc,
        result=result,
        settings=_settings_offline(),
    )
    assert "Гречка" in body
    assert "Сколько примерно было?" in body
    assert merged.clarification_question == body
    assert kb is not None
    assert any("mpt:150" in str(btn.callback_data) for row in kb.inline_keyboard for btn in row)


@pytest.mark.asyncio
async def test_build_blocking_non_portion_has_no_keyboard(monkeypatch: pytest.MonkeyPatch) -> None:
    """When primary issue is not weight (e.g. ambiguous product with estimated mass), no gram presets."""
    svc = CalorieService()
    cheese = FoodItemRecognition(
        name="Сыр",
        portion_description="40 г",
        estimated_grams=40.0,
        calories=150,
        calories_per_100g=375.0,
        protein=10.0,
        fat=12.0,
        carbs=2.0,
        food_confidence=0.85,
        portion_confidence=0.55,
        grams_source=GramsSource.DEFAULT_PORTION.value,
        confidence=0.85,
    )
    base = FoodRecognitionResult(
        items=[cheese],
        total_calories=150,
        overall_confidence=0.85,
        comment="test",
        needs_clarification=False,
    )
    result = svc.validate_food_result(base)
    result = svc.apply_clarification_guards(result)

    async def fake_card(self, ctx_inner):
        return (
            "Уточни, какой сыр — тогда точнее посчитаю.",
            ClarificationReplyPayload(
                primary_issue="ambiguous_product",
                message="Уточни, какой сыр — тогда точнее посчитаю.",
                quick_actions=[],
                expects_input_type="free_text",
            ),
        )

    monkeypatch.setattr(ClarificationReplyService, "generate_card", fake_card)
    body, kb, merged = await build_blocking_clarification_ui(
        calorie_service=svc,
        result=result,
        settings=_settings_offline(),
    )
    assert "сыр" in body.lower()
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
