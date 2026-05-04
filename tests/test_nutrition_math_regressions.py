"""Unit tests for pure nutrition arithmetic and rollup consistency (no OpenAI)."""

from __future__ import annotations

import math

import pytest

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.domain import MealSource
from calorie_bot.app.repositories.meal_repository import _sum_macros
from calorie_bot.app.services.calorie_service import CalorieService, recognition_item_mid_calories
from calorie_bot.app.services.nutrition_calculator import (
    calorie_range_from_per_100g,
    calories_from_per_100g,
    macro_g_from_per_100g,
    macro_range_from_per_100g,
)


def test_calories_and_macros_from_per_100g_point_mass() -> None:
    """KBJU for 250 g from per-100g values matches rounding rules."""
    g = 250.0
    kcal_100 = 100.0
    p100, f100, c100 = 8.0, 4.0, 8.0
    assert calories_from_per_100g(kcal_100, g) == 250
    assert macro_g_from_per_100g(p100, g) == pytest.approx(20.0)
    assert macro_g_from_per_100g(f100, g) == pytest.approx(10.0)
    assert macro_g_from_per_100g(c100, g) == pytest.approx(20.0)
    implied = 20 * 4 + 10 * 9 + 20 * 4
    assert implied == pytest.approx(250.0)


def test_range_helpers() -> None:
    """Mass range maps to kcal/macro bands."""
    lo, hi = calorie_range_from_per_100g(80.0, 100.0, 200.0)
    assert (lo, hi) == (80, 160)
    pm, pmx = macro_range_from_per_100g(4.0, 100.0, 200.0)
    assert pm == pytest.approx(4.0)
    assert pmx == pytest.approx(8.0)


def test_validate_food_result_overwrites_wrong_total_calories() -> None:
    """Server recomputes meal total from item midpoints; bogus AI total is ignored."""
    svc = CalorieService()

    def line(name: str, grams: float) -> FoodItemRecognition:
        return FoodItemRecognition(
            name=name,
            portion_description=f"{grams:.0f} г",
            estimated_grams=grams,
            calories_per_100g=100.0,
            protein_per_100g=8.0,
            fat_per_100g=4.0,
            carbs_per_100g=8.0,
            calories=round(100.0 * grams / 100.0),
            protein=round(8.0 * grams / 100.0, 1),
            fat=round(4.0 * grams / 100.0, 1),
            carbs=round(8.0 * grams / 100.0, 1),
            food_confidence=0.9,
            portion_confidence=0.85,
            grams_source="user",
        )

    items = [line("а", 100.0), line("б", 200.0)]
    expected_mid = sum(recognition_item_mid_calories(i) for i in items)
    raw = FoodRecognitionResult(
        items=items,
        total_calories=99999,
        overall_confidence=0.9,
        comment="x",
    )
    out = svc.validate_food_result(raw)
    assert out.total_calories == expected_mid == 300


def test_to_meal_draft_macros_sum_matches_items() -> None:
    """Draft rollups: calories and stored macros equal sums of item lines."""
    svc = CalorieService()
    item = FoodItemRecognition(
        name="x",
        portion_description="100 г",
        estimated_grams=100.0,
        calories_per_100g=80.0,
        protein_per_100g=10.0,
        fat_per_100g=0.0,
        carbs_per_100g=10.0,
        calories=80,
        protein=10.0,
        fat=0.0,
        carbs=10.0,
        food_confidence=0.9,
        portion_confidence=0.85,
        grams_source="user",
    )
    item2 = item.model_copy(
        update={
            "name": "y",
            "estimated_grams": 50.0,
            "portion_description": "50 г",
            "calories": 40,
            "protein": 5.0,
            "fat": 0.0,
            "carbs": 5.0,
        }
    )
    result = svc.validate_food_result(
        FoodRecognitionResult(
            items=[item, item2],
            total_calories=0,
            overall_confidence=0.9,
            comment="t",
        )
    )
    draft = svc.to_meal_draft(result, source=MealSource.TEXT)
    assert draft.total_calories == 80 + 40
    p, f, c = _sum_macros(draft.items)
    assert p == pytest.approx(15.0)
    assert f == pytest.approx(0.0)
    assert c == pytest.approx(15.0)
    assert not any(math.isnan(v) for v in (p, f, c))


def test_no_nan_in_macros_when_missing_density() -> None:
    """macro_g_from_per_100g returns None, not NaN, for unknown density."""
    assert macro_g_from_per_100g(None, 100.0) is None
