"""Atwater alignment: line kcal matches 4P+9F+4C when БЖУ are all known."""

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.utils.calories import calories_from_macros


def test_validate_aligns_inconsistent_density_to_macros() -> None:
    """Per-100g kcal and macro columns from the same bad profile → kcal fixed to macros."""
    svc = CalorieService()
    g = 100.0
    p = 0.3
    f = 0.2
    c = 13.8
    item = FoodItemRecognition(
        name="яблоко",
        portion_description=f"{g:.0f} г",
        estimated_grams=g,
        calories=52,
        calories_per_100g=52.0,
        protein_per_100g=0.26,
        fat_per_100g=0.17,
        carbs_per_100g=13.8,
        protein=p,
        fat=f,
        carbs=c,
        food_confidence=0.9,
        portion_confidence=0.85,
        confidence=0.9,
    )
    r = FoodRecognitionResult(
        items=[item],
        total_calories=52,
        overall_confidence=0.9,
        comment="t",
    )
    out = svc.validate_food_result(r)
    atw = calories_from_macros(p, f, c)
    assert out.items[0].calories == atw
    assert out.total_calories == atw
    implied_per = round(atw * 100.0 / g, 2)
    assert out.items[0].calories_per_100g == implied_per


def test_validate_skips_align_when_macros_match_density() -> None:
    """When implied energy already matches kcal, do not rewrite."""
    svc = CalorieService()
    item = FoodItemRecognition(
        name="тест",
        portion_description="100 г",
        estimated_grams=100.0,
        calories=400,
        calories_per_100g=400.0,
        protein_per_100g=50.0,
        fat_per_100g=0.0,
        carbs_per_100g=50.0,
        protein=50.0,
        fat=0.0,
        carbs=50.0,
        food_confidence=0.99,
        portion_confidence=0.99,
        confidence=0.99,
    )
    r = FoodRecognitionResult(items=[item], total_calories=400, overall_confidence=0.99, comment="t")
    out = svc.validate_food_result(r)
    assert out.items[0].calories == 400
