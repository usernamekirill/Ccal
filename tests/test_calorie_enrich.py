"""Tests for text-meal enrichment: drop mass-only lines with no kcal and hydrate wiring."""

from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.config import Settings
from calorie_bot.app.services.calorie_service import CalorieService


def _item(
    *,
    name: str,
    grams: float,
    calories: int | None,
    per_100: float | None = None,
) -> FoodItemRecognition:
    return FoodItemRecognition(
        name=name,
        portion_description=f"{grams:.0f} г",
        estimated_grams=grams,
        calories=calories,
        calories_per_100g=per_100,
        confidence=0.9,
        food_confidence=0.9,
        portion_confidence=0.9,
    )


def test_separate_uncounted_drops_quantified_zero_kcal() -> None:
    """Lines with grams but no countable calories must not appear as logged food."""
    svc = CalorieService()
    base = FoodRecognitionResult(
        items=[
            _item(name="яблоко", grams=200, calories=100, per_100=50.0),
            _item(name="пармезан", grams=50, calories=None, per_100=None),
        ],
        total_calories=100,
        overall_confidence=0.9,
        comment="t",
    )
    validated = svc.validate_food_result(base)
    out = svc.separate_uncounted_quantified_items(validated)
    assert len(out.items) == 1
    assert out.items[0].name == "яблоко"
    assert out.needs_clarification is True
    assert "пармезан" in (out.clarification_question or "")
    assert "Не смог точно посчитать" in (out.clarification_question or "")


def test_separate_uncounted_keeps_unknown_portion_lines() -> None:
    """Items without quantified mass are kept even when midpoint kcal is 0."""
    svc = CalorieService()
    base = FoodRecognitionResult(
        items=[
            FoodItemRecognition(
                name="салат",
                portion_description="порция",
                estimated_grams=None,
                calories=None,
                confidence=0.7,
            ),
        ],
        total_calories=0,
        overall_confidence=0.7,
        comment="t",
    )
    validated = svc.validate_food_result(base)
    out = svc.separate_uncounted_quantified_items(validated)
    assert len(out.items) == 1


@pytest.mark.asyncio
async def test_enrich_after_text_processing_calls_hydrate(monkeypatch: pytest.MonkeyPatch) -> None:
    """``enrich_after_text_processing`` should run hydration then separation."""
    svc = CalorieService()
    settings = Settings.model_construct(
        openai_api_key=SecretStr("sk-test"),
        telegram_bot_token=SecretStr("1:test"),
    )
    session = AsyncMock(spec=AsyncSession)

    async def fake_hydrate(
        self: CalorieService,
        result: FoodRecognitionResult,
        _session: AsyncSession,
        _settings: Settings,
    ) -> FoodRecognitionResult:
        return result

    monkeypatch.setattr(CalorieService, "hydrate_items_missing_nutrition_density", fake_hydrate)

    base = FoodRecognitionResult(
        items=[_item(name="x", grams=50, calories=None, per_100=None)],
        total_calories=0,
        overall_confidence=0.8,
        comment="t",
    )
    inp = svc.validate_food_result(base)
    out = await svc.enrich_after_text_processing(inp, "x 50 г", session, settings)
    assert out.needs_clarification is True
    assert len(out.items) == 0
