"""Countable-portion parsing (штуки / half / size) and gram integration."""

from __future__ import annotations

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.services.food_parser_service import apply_user_gram_priority
from calorie_bot.app.services.quantity_phrase_parser import parse_quantity_phrase
from calorie_bot.app.utils.nutrition_formatter import format_item_block


def _fruit(per_c: float = 52.0) -> FoodItemRecognition:
    """Single apple-like line with plausible per-100g for tests."""
    return FoodItemRecognition(
        name="яблоко",
        portion_description="порция",
        estimated_grams=136,
        calories=71,
        calories_per_100g=per_c,
        protein_per_100g=0.26,
        fat_per_100g=0.17,
        carbs_per_100g=13.8,
        protein=0.35,
        fat=0.23,
        carbs=18.8,
        food_confidence=0.9,
        portion_confidence=0.8,
        grams_source="ai_photo",
    )


def _base_result(item: FoodItemRecognition) -> FoodRecognitionResult:
    return FoodRecognitionResult(
        items=[item],
        total_calories=item.calories or 0,
        overall_confidence=0.8,
        comment="test",
    )


def test_two_apples_parsed_and_displayed() -> None:
    svc = CalorieService()
    r = svc.validate_food_result(_base_result(_fruit()))
    out = apply_user_gram_priority("2 яблока", r, svc)
    assert out.items[0].quantity == 2
    assert out.items[0].unit_type == "piece"
    assert abs(float(out.items[0].estimated_grams or 0) - 272) < 1.5
    assert out.items[0].grams_source == "user_quantity"
    block = "\n".join(format_item_block(out.items[0]))
    assert "2 шт" in block
    assert "~272" in block or "272" in block


def test_one_apple() -> None:
    svc = CalorieService()
    r = svc.validate_food_result(_base_result(_fruit()))
    out = apply_user_gram_priority("1 яблоко", r, svc)
    assert out.items[0].quantity == 1
    assert abs(float(out.items[0].estimated_grams or 0) - 136) < 1.5


def test_three_pancakes_reference_weight() -> None:
    """Countable блины without explicit grams use reference unit mass × quantity."""
    svc = CalorieService()
    line = FoodItemRecognition(
        name="блин",
        portion_description="порция",
        estimated_grams=55.0,
        calories=150,
        calories_per_100g=200.0,
        protein_per_100g=5.0,
        fat_per_100g=6.0,
        carbs_per_100g=30.0,
        food_confidence=0.9,
        portion_confidence=0.8,
        grams_source="ai_photo",
    )
    r = svc.validate_food_result(_base_result(line))
    out = apply_user_gram_priority("3 блина", r, svc)
    assert out.items[0].quantity == 3
    assert abs(float(out.items[0].estimated_grams or 0) - 165.0) < 1.5


def test_two_syrniki_word_quantity() -> None:
    svc = CalorieService()
    line = FoodItemRecognition(
        name="сырник",
        portion_description="порция",
        estimated_grams=70.0,
        calories=210,
        calories_per_100g=300.0,
        protein_per_100g=12.0,
        fat_per_100g=15.0,
        carbs_per_100g=30.0,
        food_confidence=0.9,
        portion_confidence=0.8,
        grams_source="ai_photo",
    )
    r = svc.validate_food_result(_base_result(line))
    out = apply_user_gram_priority("два сырника", r, svc)
    assert out.items[0].quantity == 2
    assert abs(float(out.items[0].estimated_grams or 0) - 140.0) < 1.5


def test_two_pancakes_seventy_g_each_total_mass() -> None:
    """«2 блина по 70 г» → 140 г total despite other gram tokens in phrase."""
    svc = CalorieService()
    line = FoodItemRecognition(
        name="блин",
        portion_description="порция",
        estimated_grams=55.0,
        calories=100,
        calories_per_100g=180.0,
        protein_per_100g=6.0,
        fat_per_100g=3.0,
        carbs_per_100g=25.0,
        food_confidence=0.9,
        portion_confidence=0.8,
        grams_source="ai_photo",
    )
    r = svc.validate_food_result(_base_result(line))
    out = apply_user_gram_priority("2 блина по 70 г", r, svc)
    assert abs(float(out.items[0].estimated_grams or 0) - 140.0) < 1.5
    assert out.items[0].unit_weight_grams == 70.0


def test_two_apples_word_form() -> None:
    """Spelled-out Russian quantities («два яблока») should match digit form."""
    svc = CalorieService()
    r = svc.validate_food_result(_base_result(_fruit()))
    out = apply_user_gram_priority("два яблока", r, svc)
    assert out.items[0].quantity == 2
    assert abs(float(out.items[0].estimated_grams or 0) - 272) < 1.5


def test_half_apple_via_phrase_parser() -> None:
    p = parse_quantity_phrase("половина яблока")
    assert p is not None
    assert p.quantity == 0.5


def test_half_apple_grams() -> None:
    svc = CalorieService()
    r = svc.validate_food_result(_base_result(_fruit()))
    out = apply_user_gram_priority("половина яблока", r, svc)
    assert out.items[0].quantity == 0.5
    assert abs(float(out.items[0].estimated_grams or 0) - 68) < 2


def test_large_apple() -> None:
    svc = CalorieService()
    r = svc.validate_food_result(_base_result(_fruit()))
    out = apply_user_gram_priority("большое яблоко", r, svc)
    assert out.items[0].size_modifier == "large"
    assert abs(float(out.items[0].estimated_grams or 0) - 180) < 1.5


def test_two_small_apples() -> None:
    svc = CalorieService()
    r = svc.validate_food_result(_base_result(_fruit()))
    out = apply_user_gram_priority("2 маленьких яблока", r, svc)
    assert out.items[0].quantity == 2
    assert out.items[0].size_modifier == "small"
    assert abs(float(out.items[0].estimated_grams or 0) - 200) < 1.5


def test_explicit_grams_clear_quantity_semantics() -> None:
    svc = CalorieService()
    r = svc.validate_food_result(_base_result(_fruit()))
    out = apply_user_gram_priority("яблоко 150 г", r, svc)
    assert out.items[0].quantity is None
    assert out.items[0].unit_type is None
    assert out.items[0].estimated_grams == 150
    block = "\n".join(format_item_block(out.items[0]))
    assert "150 г" in block
    assert "шт" not in block


def test_edit_instruction_make_two_apples() -> None:
    svc = CalorieService()
    r = svc.validate_food_result(_base_result(_fruit()))
    out = apply_user_gram_priority("сделай 2 яблока", r, svc)
    assert out.items[0].quantity == 2
    assert out.items[0].grams_source == "user_quantity"


def test_edit_one_apple_recalculates_macros() -> None:
    svc = CalorieService()
    r = svc.validate_food_result(_base_result(_fruit()))
    out = apply_user_gram_priority("это 1 яблоко", r, svc)
    assert out.items[0].quantity == 1
    g = float(out.items[0].estimated_grams or 0)
    assert abs(g - 136) < 2
    assert out.items[0].calories is not None
    assert out.items[0].protein is not None


def test_two_bread_slices() -> None:
    item = FoodItemRecognition(
        name="хлеб",
        portion_description="порция",
        estimated_grams=30,
        calories=75,
        calories_per_100g=250,
        protein_per_100g=8,
        fat_per_100g=3,
        carbs_per_100g=50,
        food_confidence=0.9,
        portion_confidence=0.7,
        grams_source="ai_photo",
    )
    svc = CalorieService()
    r = svc.validate_food_result(_base_result(item))
    out = apply_user_gram_priority("2 кусочка хлеба", r, svc)
    assert out.items[0].unit_type == "slice"
    assert out.items[0].quantity == 2
    assert abs(float(out.items[0].estimated_grams or 0) - 60) < 1.5
