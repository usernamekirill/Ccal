"""Acceptance-style tests on synthetic FoodRecognitionResult (mock LLM JSON), no OpenAI."""

from __future__ import annotations

import pytest

from calorie_bot.app.ai.schemas import (
    FoodItemRecognition,
    FoodRecognitionResult,
    VisionPhotoAnalysisItem,
    VisionPhotoAnalysisResult,
)
from calorie_bot.app.domain import MealSource
from calorie_bot.app.services.calorie_service import CalorieService, recognition_item_mid_calories
from calorie_bot.app.services.food_parser_service import apply_user_gram_priority


def _result(*, items: list[FoodItemRecognition], total_wrong: int = 0) -> FoodRecognitionResult:
    return FoodRecognitionResult(
        items=list(items),
        total_calories=total_wrong,
        overall_confidence=0.85,
        comment="synthetic",
    )


def _line_user(
    name: str,
    grams: float,
    *,
    kcal_100: float = 100.0,
    p100: float = 10.0,
    f100: float = 5.0,
    c100: float = 20.0,
) -> FoodItemRecognition:
    """One recognition line with Atwater-consistent macros (4/9/4 matches kcal)."""
    cal = round(kcal_100 * grams / 100.0)
    p = round(p100 * grams / 100.0, 1)
    f = round(f100 * grams / 100.0, 1)
    c = round(c100 * grams / 100.0, 1)
    return FoodItemRecognition(
        name=name,
        portion_description=f"{grams:.0f} г",
        estimated_grams=grams,
        calories_per_100g=kcal_100,
        protein_per_100g=p100,
        fat_per_100g=f100,
        carbs_per_100g=c100,
        calories=cal,
        protein=p,
        fat=f,
        carbs=c,
        food_confidence=0.9,
        portion_confidence=0.88,
        grams_source="user",
        needs_portion_clarification=False,
        is_estimated=False,
    )


def test_two_items_buckwheat_chicken_explicit_weights() -> None:
    """«гречка 200 г и курица 150 г» — два item, веса и сумма total."""
    svc = CalorieService()
    g = _line_user("гречка", 200.0, kcal_100=110.0, p100=4.0, f100=1.0, c100=22.0)
    ch = _line_user("курица", 150.0, kcal_100=165.0, p100=22.0, f100=7.0, c100=0.0)
    out = svc.validate_food_result(_result(items=[g, ch]))
    assert len(out.items) == 2
    assert out.items[0].estimated_grams == 200
    assert out.items[1].estimated_grams == 150
    mid = sum(recognition_item_mid_calories(i) for i in out.items)
    assert out.total_calories == mid
    draft = svc.to_meal_draft(out, source=MealSource.TEXT)
    assert draft.total_calories == mid


def test_pancakes_and_sour_cream_two_lines() -> None:
    """«5 блинов со сметаной» как два item от LLM — сумма калорий общая."""
    svc = CalorieService()
    pan = _line_user("блин", 275.0, kcal_100=200.0, p100=6.0, f100=6.0, c100=28.0)
    sm = _line_user("сметана", 30.0, kcal_100=193.0, p100=2.8, f100=20.0, c100=3.2)
    out = svc.validate_food_result(_result(items=[pan, sm]))
    assert len(out.items) >= 2
    assert out.total_calories == sum(recognition_item_mid_calories(i) for i in out.items)


def test_coffee_milk_sugar_three_items() -> None:
    """Три компонента — ничего не схлопывается на уровне валидации."""
    svc = CalorieService()
    items = [
        _line_user("кофе", 200.0, kcal_100=2.0, p100=0.1, f100=0.2, c100=0.3),
        _line_user("молоко", 40.0, kcal_100=50.0, p100=3.0, f100=1.5, c100=4.5),
        _line_user("сахар", 10.0, kcal_100=400.0, p100=0.0, f100=0.0, c100=100.0),
    ]
    out = svc.validate_food_result(_result(items=items))
    assert len(out.items) == 3
    names = {i.name for i in out.items}
    assert names == {"кофе", "молоко", "сахар"}


def test_tvorog_fat_and_weight_single_line() -> None:
    """«творог 5% 200 г» — одна строка, процент в name, масса 200."""
    svc = CalorieService()
    row = _line_user("творог 5%", 200.0, kcal_100=121.0, p100=17.0, f100=5.0, c100=1.8)
    out = svc.validate_food_result(_result(items=[row]))
    assert len(out.items) == 1
    assert "5%" in out.items[0].name or "5" in out.items[0].name
    assert out.items[0].estimated_grams == 200


def test_salad_ambiguous_triggers_clarification_guard() -> None:
    """Короткое «салат» с оценочной порцией должно требовать уточнения."""
    svc = CalorieService()
    row = FoodItemRecognition(
        name="салат",
        portion_description="порция",
        estimated_grams=150.0,
        calories_per_100g=50.0,
        protein_per_100g=1.5,
        fat_per_100g=3.0,
        carbs_per_100g=5.0,
        calories=75,
        protein=2.2,
        fat=4.5,
        carbs=7.5,
        food_confidence=0.55,
        portion_confidence=0.5,
        grams_source="default_portion",
        is_estimated=True,
    )
    base = svc.validate_food_result(_result(items=[row]))
    guarded = svc.apply_clarification_guards(base)
    assert guarded.needs_clarification is True
    assert guarded.clarification_question
    # Не должны быть «жёстко уверенные» уровни у самого item при generic name + weak signals
    assert guarded.items[0].food_confidence <= 0.95


def test_banana_and_apple_two_items_total_sum() -> None:
    svc = CalorieService()
    a = _line_user("банан", 120.0, kcal_100=89.0, p100=1.1, f100=0.3, c100=23.0)
    b = _line_user("яблоко", 130.0, kcal_100=52.0, p100=0.3, f100=0.2, c100=14.0)
    out = svc.validate_food_result(_result(items=[a, b]))
    assert len(out.items) == 2
    mid01 = recognition_item_mid_calories(out.items[0])
    mid01 += recognition_item_mid_calories(out.items[1])
    assert out.total_calories == mid01


def test_three_eggs_quantity_from_user_text() -> None:
    """«три яйца» на одной строке LLM — локальное количество через quantity parser."""
    svc = CalorieService()
    egg = FoodItemRecognition(
        name="яйцо",
        portion_description="1 шт",
        estimated_grams=60.0,
        calories_per_100g=157.0,
        protein_per_100g=13.0,
        fat_per_100g=11.0,
        carbs_per_100g=1.0,
        calories=94,
        protein=7.8,
        fat=6.6,
        carbs=0.6,
        food_confidence=0.9,
        portion_confidence=0.85,
        grams_source="unknown",
    )
    base = svc.validate_food_result(_result(items=[egg]))
    out = apply_user_gram_priority("три яйца", base, svc)
    assert out.items[0].quantity == 3
    assert out.items[0].unit_type == "piece"
    assert float(out.items[0].estimated_grams or 0) == pytest.approx(150.0, rel=0.05)


def test_two_apples_calories_gt_single_apple() -> None:
    """«2 яблока» — калорийность выше одного яблока после quantity."""
    svc = CalorieService()
    apple = FoodItemRecognition(
        name="яблоко",
        portion_description="порция",
        estimated_grams=136.0,
        calories_per_100g=52.0,
        protein_per_100g=0.3,
        fat_per_100g=0.2,
        carbs_per_100g=14.0,
        calories=71,
        protein=0.4,
        fat=0.3,
        carbs=19.0,
        food_confidence=0.9,
        portion_confidence=0.85,
        grams_source="ai_photo",
    )
    one = svc.validate_food_result(_result(items=[apple]))
    two = apply_user_gram_priority("2 яблока", one, svc)
    assert two.items[0].quantity == 2
    assert (two.items[0].calories or 0) > (one.items[0].calories or 0)


def test_omelette_eggs_and_cheese_two_items() -> None:
    """Омлет: яйца с quantity=3 и сыр отдельной строкой (синтетика LLM)."""
    svc = CalorieService()
    eggs = FoodItemRecognition(
        name="яйцо куриное",
        portion_description="3 шт",
        estimated_grams=180.0,
        calories_per_100g=157.0,
        protein_per_100g=13.0,
        fat_per_100g=11.0,
        carbs_per_100g=1.0,
        calories=283,
        protein=23.4,
        fat=19.8,
        carbs=1.8,
        food_confidence=0.88,
        portion_confidence=0.8,
        grams_source="user",
        quantity=3.0,
        unit_type="piece",
    )
    cheese = FoodItemRecognition(
        name="сыр",
        portion_description="оценка",
        estimated_grams=40.0,
        calories_per_100g=350.0,
        protein_per_100g=25.0,
        fat_per_100g=28.0,
        carbs_per_100g=0.5,
        calories=140,
        protein=10.0,
        fat=11.2,
        carbs=0.2,
        food_confidence=0.6,
        portion_confidence=0.45,
        grams_source="default_portion",
        needs_portion_clarification=True,
    )
    out = svc.validate_food_result(_result(items=[eggs, cheese]))
    assert len(out.items) == 2
    assert out.items[0].quantity == 3
    assert "сыр" in out.items[1].name


def test_vision_two_dishes_totals_equal_sum() -> None:
    """Фото: два item — total_calories после validate = сумма строк."""
    svc = CalorieService()
    raw = VisionPhotoAnalysisResult(
        items=[
            VisionPhotoAnalysisItem(
                name="борщ",
                portion_description="тарелка",
                estimated_grams=320.0,
                calories_per_100g=52.0,
                protein_per_100g=2.5,
                fat_per_100g=2.2,
                carbs_per_100g=6.0,
                food_confidence=0.82,
                portion_confidence=0.7,
            ),
            VisionPhotoAnalysisItem(
                name="сметана",
                estimated_grams=25.0,
                calories_per_100g=193.0,
                protein_per_100g=2.8,
                fat_per_100g=20.0,
                carbs_per_100g=3.2,
                food_confidence=0.78,
                portion_confidence=0.65,
            ),
        ],
        meal_type="lunch",
        overall_confidence=0.8,
        comment="обед",
    )
    out = svc.from_vision_photo_analysis(raw)
    s = sum(recognition_item_mid_calories(i) for i in out.items)
    assert out.total_calories == s
    draft = svc.to_meal_draft(out, source=MealSource.PHOTO)
    assert draft.total_calories == s
