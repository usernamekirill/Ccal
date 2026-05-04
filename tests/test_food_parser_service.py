"""Tests for user gram extraction and priority over AI portion estimates."""

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.services.food_parser_service import (
    apply_user_gram_priority,
    extract_ordered_gram_values,
    parse_loose_grams_line,
)


def _item(
    name: str,
    grams: float,
    calories: int,
) -> FoodItemRecognition:
    per = round(calories * 100.0 / grams, 2) if grams else 200.0
    return FoodItemRecognition(
        name=name,
        portion_description=f"{grams:.0f} г",
        estimated_grams=grams,
        calories=calories,
        calories_per_100g=per,
        protein=10.0,
        fat=10.0,
        carbs=40.0,
        confidence=0.9,
        food_confidence=0.9,
        portion_confidence=0.9,
    )


def _result(items: list[FoodItemRecognition]) -> FoodRecognitionResult:
    total = sum(i.calories for i in items)
    return FoodRecognitionResult(
        items=items,
        total_calories=total,
        overall_confidence=min(i.confidence for i in items),
        comment="тест",
    )


def test_parse_loose_grams_line_accepts_bare_number_and_suffix() -> None:
    """FSM weight step: whole message is grams only (no LLM)."""
    assert parse_loose_grams_line("100") == 100.0
    assert parse_loose_grams_line("120.5г") == 120.5
    assert parse_loose_grams_line("  80 г ") == 80.0
    assert parse_loose_grams_line("яблоко") is None
    assert parse_loose_grams_line("") is None


def test_extract_ordered_gram_values_finds_mass_units() -> None:
    """Explicit grams in Russian text should be extracted in reading order."""
    assert extract_ordered_gram_values("половина кулича 50 г") == [50.0]
    assert extract_ordered_gram_values("рис 100 г, курица 200 г") == [100.0, 200.0]
    assert extract_ordered_gram_values("50г борща") == [50.0]


def test_apply_user_gram_priority_single_item_scales_calories() -> None:
    """When the user states 50 g and AI used 150 g, calories scale linearly."""
    svc = CalorieService()
    raw = _result([_item("кулич", 150, 450)])
    out = apply_user_gram_priority("половина кулича 50 г", raw, svc)
    assert out.items[0].estimated_grams == 50
    assert out.items[0].calories == 150
    assert out.total_calories == 150


def test_apply_user_gram_priority_multi_item_matches_ordered_grams() -> None:
    """Same number of gram hints as items applies positionally."""
    svc = CalorieService()
    raw = _result(
        [
            _item("рис", 200, 260),
            _item("курица", 150, 280),
        ]
    )
    out = apply_user_gram_priority("рис 100 г курица 120 г", raw, svc)
    assert out.items[0].estimated_grams == 100
    assert out.items[1].estimated_grams == 120
    assert out.total_calories == out.items[0].calories + out.items[1].calories


def test_apply_user_gram_priority_lone_gram_picks_nearest_name() -> None:
    """One gram hint among several items should attach to the most plausible line."""
    svc = CalorieService()
    raw = _result(
        [
            _item("салат", 100, 50),
            _item("кулич", 150, 450),
        ]
    )
    out = apply_user_gram_priority("салат и кулич, съел 50 г", raw, svc)
    assert out.items[1].estimated_grams == 50
    assert out.items[1].calories == 150
