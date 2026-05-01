from types import SimpleNamespace

import pytest

from calorie_bot.app.domain import MealItemDraft
from calorie_bot.app.services.calorie_service import (
    CalorieService,
    NutritionEstimate,
    normalize_food_name,
)


class FakeFoodCacheRepository:
    """In-memory food cache repository for service tests."""

    def __init__(self, cached=None) -> None:
        self.cached = cached
        self.upsert_calls = []

    async def get_by_normalized_name(self, normalized_name: str):
        """Return cached item by normalized name."""
        return self.cached

    async def upsert(self, **kwargs):
        """Store cache write and return cache-like object."""
        self.upsert_calls.append(kwargs)
        self.cached = SimpleNamespace(**kwargs)
        return self.cached


class FakeEstimator:
    """Fake AI estimator for service tests."""

    def __init__(self) -> None:
        self.calls = []

    async def estimate_food(self, food_name: str) -> NutritionEstimate:
        """Return deterministic nutrition estimate."""
        self.calls.append(food_name)
        return NutritionEstimate(
            display_name="гречка",
            calories_per_100g=110,
            protein_per_100g=4,
            fat_per_100g=1,
            carbs_per_100g=22,
            confidence=0.8,
        )


def test_normalizes_food_name() -> None:
    """Food names should be normalized for cache lookup."""
    assert normalize_food_name("  Гречка, с МАСЛОМ!  ") == "гречка с маслом"


def test_calculates_item_and_meal_calories() -> None:
    """Calorie service should calculate item and meal calories."""
    service = CalorieService()

    item_calories = service.calculate_item_calories(calories_per_100g=110, grams=200)
    meal_calories = service.calculate_meal_calories(
        [
            MealItemDraft(name="гречка", calories=item_calories, grams=200),
            MealItemDraft(name="курица", calories=250, grams=150),
        ]
    )

    assert item_calories == 220
    assert meal_calories == 470


@pytest.mark.asyncio
async def test_uses_food_cache_before_ai_estimator() -> None:
    """Cached food should avoid an AI estimator call."""
    cached = SimpleNamespace(
        display_name="гречка",
        calories_per_100g=110,
        protein_per_100g=4,
        fat_per_100g=1,
        carbs_per_100g=22,
        confidence=0.9,
    )
    estimator = FakeEstimator()

    item = await CalorieService().get_or_estimate_food(
        food_name="Гречка",
        grams=200,
        cache_repository=FakeFoodCacheRepository(cached=cached),
        estimator=estimator,
    )

    assert item.calories == 220
    assert item.protein == 8
    assert estimator.calls == []


@pytest.mark.asyncio
async def test_estimates_and_caches_food_when_missing() -> None:
    """Missing cache item should call estimator and save result."""
    cache = FakeFoodCacheRepository()
    estimator = FakeEstimator()

    item = await CalorieService().get_or_estimate_food(
        food_name="Гречка",
        grams=100,
        cache_repository=cache,
        estimator=estimator,
    )

    assert item.calories == 110
    assert estimator.calls == ["Гречка"]
    assert cache.upsert_calls[0]["normalized_name"] == "гречка"


@pytest.mark.parametrize(
    ("calories", "grams"),
    [(-1, 100), (5001, 100), (100, 5001)],
)
def test_rejects_unrealistic_values(calories: int, grams: int) -> None:
    """Calorie service should reject unsafe item values."""
    service = CalorieService()
    with pytest.raises(ValueError):
        service.validate_item(MealItemDraft(name="test", calories=calories, grams=grams))
