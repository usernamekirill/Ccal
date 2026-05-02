"""Tests for honest portion handling and CalorieService vision pipeline."""

import pytest

from calorie_bot.app.ai.schemas import (
    FoodItemRecognition,
    FoodRecognitionResult,
    VisionPhotoAnalysisItem,
    VisionPhotoAnalysisResult,
)
from calorie_bot.app.domain import GramsSource
from calorie_bot.app.services.calorie_service import CalorieService


def test_vision_without_grams_uses_default_range() -> None:
    """When AI omits grams, default portion range and per-100g drive a calorie band."""
    raw = VisionPhotoAnalysisResult(
        items=[
            VisionPhotoAnalysisItem(
                name="кулич",
                calories_per_100g=300,
                protein_per_100g=8,
                fat_per_100g=12,
                carbs_per_100g=50,
                food_confidence=0.8,
                portion_confidence=0.45,
            ),
        ],
        comment="test",
    )
    out = CalorieService().from_vision_photo_analysis(raw)
    assert out.items[0].grams_min is not None and out.items[0].grams_max is not None
    assert out.items[0].grams_source == "default_portion"
    assert out.items[0].calories is None
    assert out.items[0].calories_min is not None and out.items[0].calories_max is not None
    assert out.total_calories_min is not None and out.total_calories_max is not None


def test_user_grams_override_ai_photo() -> None:
    """Explicit user grams win over AI point estimate (150 -> 50)."""
    svc = CalorieService()
    r = FoodRecognitionResult(
        items=[
            FoodItemRecognition(
                name="рис",
                portion_description="150 г",
                estimated_grams=150,
                calories=195,
                calories_per_100g=130,
                protein=4.8,
                fat=0.9,
                carbs=42.9,
                food_confidence=0.8,
                portion_confidence=0.7,
                grams_source="ai_photo",
            ),
        ],
        total_calories=195,
        overall_confidence=0.7,
        comment="t",
    )
    r = svc.validate_food_result(r)
    from calorie_bot.app.services.food_parser_service import apply_user_gram_priority

    out = apply_user_gram_priority("50 г", r, svc, grams_source=GramsSource.USER.value)
    assert out.items[0].estimated_grams == 50
    assert out.items[0].calories == 65
    assert out.items[0].grams_source == "user"


def test_grams_source_user_not_overwritten_by_lower_rank_merge() -> None:
    """User-sourced grams must not be replaced by weaker AI merge helper."""
    svc = CalorieService()
    item = FoodItemRecognition(
        name="x",
        portion_description="50 г",
        estimated_grams=50,
        calories=100,
        calories_per_100g=200,
        grams_source="user",
        food_confidence=0.9,
        portion_confidence=0.9,
    )
    item = svc.validate_food_result(
        FoodRecognitionResult(items=[item], total_calories=100, overall_confidence=0.9, comment="t"),
    ).items[0]
    merged = svc.merge_ai_grams_if_weaker_source(item, ai_grams=200.0, ai_grams_min=None, ai_grams_max=None)
    assert merged.estimated_grams == 50


@pytest.mark.parametrize(
    ("portion_c", "dense_name", "expect_clarify"),
    [
        (0.5, "рис", True),
        (0.55, "торт", True),
        (0.72, "торт", True),
        (0.8, "торт", False),
        (0.5, "салат", True),
        (0.7, "салат", False),
    ],
)
def test_portion_clarification_thresholds(
    portion_c: float,
    dense_name: str,
    expect_clarify: bool,
) -> None:
    """Low portion_confidence or dense food triggers clarification flags."""
    raw = VisionPhotoAnalysisResult(
        items=[
            VisionPhotoAnalysisItem(
                name=dense_name,
                estimated_grams=100,
                calories_per_100g=250,
                food_confidence=0.85,
                portion_confidence=portion_c,
            ),
        ],
        comment="t",
    )
    out = CalorieService().from_vision_photo_analysis(raw)
    assert out.items[0].needs_portion_clarification is expect_clarify


def test_calories_computed_from_grams_and_per_100g() -> None:
    svc = CalorieService()
    assert svc.calculate_item_calories(200, 50) == 100


def test_format_unknown_portion_requests_weight() -> None:
    from calorie_bot.app.utils import ux_formatter

    r = FoodRecognitionResult(
        items=[
            FoodItemRecognition(
                name="булка",
                portion_description="порция",
                estimated_grams=None,
                grams_min=None,
                grams_max=None,
                calories=None,
                calories_per_100g=400,
                food_confidence=0.6,
                portion_confidence=0.3,
            ),
        ],
        total_calories=0,
        overall_confidence=0.5,
        comment="ok",
    )
    r = CalorieService().validate_food_result(r)
    text = ux_formatter.format_meal_review(r)
    assert "Порция неясна" in text
    assert "50 г" in text


def test_phantom_calories_cleared_without_portion_mass() -> None:
    """Legacy rows with kcal but no grams/range must not show fake precision."""
    svc = CalorieService()
    r = FoodRecognitionResult(
        items=[
            FoodItemRecognition(
                name="булка",
                portion_description="порция",
                estimated_grams=None,
                grams_min=None,
                grams_max=None,
                calories=250,
                calories_per_100g=400,
                food_confidence=0.6,
                portion_confidence=0.3,
            ),
        ],
        total_calories=250,
        overall_confidence=0.5,
        comment="ok",
    )
    out = svc.validate_food_result(r)
    assert out.items[0].calories is None
    assert out.total_calories == 0
    assert out.items[0].needs_portion_clarification is True


def test_macros_hidden_for_ai_estimate_low_portion_confidence() -> None:
    """Оценочная порция с низкой уверенностью: ккал с ≈, без строки БЖУ."""
    from calorie_bot.app.utils.nutrition_formatter import format_item_block

    item = FoodItemRecognition(
        name="курица",
        portion_description="150 г",
        estimated_grams=150,
        calories=220,
        protein=30,
        fat=10,
        carbs=0,
        calories_per_100g=146.7,
        protein_per_100g=20,
        fat_per_100g=6.7,
        carbs_per_100g=0,
        grams_source="ai_photo",
        is_estimated=True,
        portion_confidence=0.55,
        food_confidence=0.82,
    )
    block = "\n".join(format_item_block(item))
    assert "Б " not in block
    assert "~150" in block
    assert "≈ 220" in block


def test_macros_shown_for_user_grams() -> None:
    from calorie_bot.app.utils.nutrition_formatter import format_item_block

    item = FoodItemRecognition(
        name="курица",
        portion_description="150 г",
        estimated_grams=150,
        calories=220,
        protein=30,
        fat=10,
        carbs=0,
        calories_per_100g=146.7,
        protein_per_100g=20,
        fat_per_100g=6.7,
        carbs_per_100g=0,
        grams_source="user",
        is_estimated=False,
        portion_confidence=1.0,
        food_confidence=1.0,
    )
    block = "\n".join(format_item_block(item))
    assert "220 ккал" in block
    assert "Б 30" in block


def test_ordinal_first_item_gets_grams() -> None:
    from calorie_bot.app.services.food_parser_service import apply_user_gram_priority

    svc = CalorieService()
    r = svc.validate_food_result(
        FoodRecognitionResult(
            items=[
                FoodItemRecognition(
                    name="суп",
                    portion_description="300 г",
                    estimated_grams=300,
                    calories=180,
                    calories_per_100g=60,
                    food_confidence=0.8,
                    portion_confidence=0.7,
                ),
                FoodItemRecognition(
                    name="салат",
                    portion_description="150 г",
                    estimated_grams=150,
                    calories=75,
                    calories_per_100g=50,
                    food_confidence=0.8,
                    portion_confidence=0.7,
                ),
            ],
            total_calories=255,
            overall_confidence=0.7,
            comment="t",
        )
    )
    out = apply_user_gram_priority("первое 50 г", r, svc)
    assert out.items[0].estimated_grams == 50
    assert out.items[1].estimated_grams == 150
