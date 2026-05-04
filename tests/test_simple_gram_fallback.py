"""Colloquial gram tokens and LLM-offline meal text fallbacks."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.services.food_parser_service import (
    extract_ordered_gram_values,
    try_simple_gram_meal_text,
)


def test_gram_pattern_accepts_colloquial_gram() -> None:
    assert extract_ordered_gram_values("гречка 150 грам") == [150.0]
    assert extract_ordered_gram_values("170 грам шарлотки") == [170.0]
    assert extract_ordered_gram_values("гречка 200г") == [200.0]
    assert extract_ordered_gram_values("50 граммов овсянки") == [50.0]


def test_try_simple_gram_meal_text_parses_name_before_or_after_grams() -> None:
    r = try_simple_gram_meal_text("170 грам шарлотки")
    assert r and len(r.items) == 1
    assert "шарлот" in r.items[0].name.lower()
    assert r.items[0].estimated_grams == 170.0

    r2 = try_simple_gram_meal_text("гречка 200г")
    assert r2 and r2.items[0].name.lower().startswith("гречк")
    assert r2.items[0].estimated_grams == 200.0


def test_try_simple_returns_none_for_multi_gram_or_no_food() -> None:
    assert try_simple_gram_meal_text("гречка 100 г + суп 200 г") is None
    assert try_simple_gram_meal_text("200г") is None
    assert try_simple_gram_meal_text("просто гречка") is None


@pytest.mark.asyncio
async def test_get_or_estimate_food_survives_estimator_exception() -> None:
    """When the density API fails, use a coarse per-100g fallback so the meal flow does not die."""
    svc = CalorieService()
    cache = AsyncMock()
    cache.get_by_normalized_name = AsyncMock(return_value=None)    
    from types import SimpleNamespace

    cache.upsert = AsyncMock(
        return_value=SimpleNamespace(
            display_name="гречка",
            calories_per_100g=200.0,
            protein_per_100g=6.0,
            fat_per_100g=5.0,
            carbs_per_100g=30.0,
            confidence=0.35,
        )
    )
    est = AsyncMock()
    est.estimate_food = AsyncMock(side_effect=RuntimeError("openai down"))

    row = await svc.get_or_estimate_food("гречка", 200.0, cache, est)
    assert row.calories is not None and row.calories > 0
    assert row.calories_per_100g is not None
    cache.upsert.assert_awaited_once()
