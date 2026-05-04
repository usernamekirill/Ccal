"""Contract tests: product without weight, grams-only line, UX copy (no OpenAI)."""

from __future__ import annotations

import pytest

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.domain import MealSource
from calorie_bot.app.nlp.meal_text_preprocess import try_grams_only_clarification
from calorie_bot.app.services.calorie_service import CalorieService, recognition_item_mid_calories
from calorie_bot.app.services.food_parser_service import apply_user_gram_priority
from calorie_bot.app.utils import ux_formatter


def _single_item_no_mass(name: str) -> FoodRecognitionResult:
    """Simulates LLM output: recognized name, no grams yet."""
    return FoodRecognitionResult(
        items=[
            FoodItemRecognition(
                name=name,
                portion_description="порция",
                estimated_grams=None,
                grams_min=None,
                grams_max=None,
                calories=999,
                calories_per_100g=100.0,
                protein_per_100g=5.0,
                fat_per_100g=2.0,
                carbs_per_100g=15.0,
                food_confidence=0.85,
                portion_confidence=0.55,
                grams_source="unknown",
            )
        ],
        total_calories=999,
        overall_confidence=0.85,
        comment="mock",
        needs_clarification=False,
    )


@pytest.mark.parametrize(
    "name",
    ["гречка", "пирог", "салат", "рис", "курица"],
)
def test_single_product_without_weight_does_not_crash_and_asks_clarification(name: str) -> None:
    """Incomplete input (no mass) is not a hard error: one item, no fake kcal, clarification set."""
    svc = CalorieService()
    raw = _single_item_no_mass(name)
    out = svc.validate_food_result(raw)
    assert len(out.items) == 1
    assert out.items[0].name == name
    assert out.items[0].calories is None
    assert out.items[0].needs_portion_clarification is True
    assert out.needs_clarification is True
    assert out.clarification_question
    assert "Я нашёл:" in out.clarification_question
    assert name in out.clarification_question
    assert out.total_calories == 0


def test_grechka_clarification_matches_product_copy_contract() -> None:
    svc = CalorieService()
    out = svc.validate_food_result(_single_item_no_mass("гречка"))
    assert "стандартную порцию (~175 г)" in out.clarification_question


def test_format_meal_review_incomplete_single_item_intro() -> None:
    svc = CalorieService()
    out = svc.validate_food_result(_single_item_no_mass("гречка"))
    text = ux_formatter.format_meal_review(out)
    assert "Я нашёл: гречка" in text
    assert "стандартную порцию" in text


def test_grams_only_line_needs_product_clarification() -> None:
    raw = try_grams_only_clarification("200 г")
    assert raw is not None
    out = CalorieService().validate_food_result(raw)
    assert out.items == []
    assert out.needs_clarification is True
    assert out.clarification_question
    assert "продукт" in out.clarification_question.lower()


def test_tvorog_five_percent_without_grams_one_item_clarifies() -> None:
    svc = CalorieService()
    raw = FoodRecognitionResult(
        items=[
            FoodItemRecognition(
                name="творог 5%",
                portion_description="порция",
                estimated_grams=None,
                calories_per_100g=90.0,
                protein_per_100g=10.0,
                fat_per_100g=5.0,
                carbs_per_100g=2.0,
                food_confidence=0.8,
                portion_confidence=0.5,
                grams_source="unknown",
            )
        ],
        total_calories=0,
        overall_confidence=0.8,
        comment="m",
    )
    out = svc.validate_food_result(raw)
    assert len(out.items) == 1
    assert "творог" in out.items[0].name and "5" in out.items[0].name.replace(" ", "")
    assert out.needs_clarification is True


def test_vision_style_total_reccomputed_when_ai_total_wrong() -> None:
    svc = CalorieService()
    a = FoodItemRecognition(
        name="а",
        portion_description="100 г",
        estimated_grams=100.0,
        calories_per_100g=100.0,
        protein_per_100g=10.0,
        fat_per_100g=0.0,
        carbs_per_100g=10.0,
        calories=100,
        protein=10.0,
        fat=0.0,
        carbs=10.0,
        food_confidence=0.9,
        portion_confidence=0.85,
        grams_source="user",
    )
    b = a.model_copy(
        update={
            "name": "б",
            "calories": 200,
        }
    )
    raw = FoodRecognitionResult(
        items=[a, b],
        total_calories=99999,
        overall_confidence=0.9,
        comment="x",
    )
    out = svc.validate_food_result(raw)
    assert out.total_calories == sum(recognition_item_mid_calories(i) for i in out.items)


def test_apple_bare_name_applies_reference_piece_weight() -> None:
    svc = CalorieService()
    apple = FoodItemRecognition(
        name="яблоко",
        portion_description="порция",
        estimated_grams=None,
        calories_per_100g=52.0,
        protein_per_100g=0.3,
        fat_per_100g=0.2,
        carbs_per_100g=14.0,
        food_confidence=0.88,
        portion_confidence=0.5,
        grams_source="unknown",
    )
    base = svc.validate_food_result(
        FoodRecognitionResult(
            items=[apple],
            total_calories=0,
            overall_confidence=0.88,
            comment="t",
        )
    )
    assert base.needs_clarification is True
    out = apply_user_gram_priority("яблоко", base, svc)
    assert out.items[0].quantity == 1
    assert out.items[0].estimated_grams is not None
    assert 130 <= float(out.items[0].estimated_grams) <= 145
    assert out.needs_clarification is False
    draft = svc.to_meal_draft(out, source=MealSource.TEXT)
    assert draft.total_calories == recognition_item_mid_calories(out.items[0])


@pytest.mark.asyncio
async def test_today_stats_three_meals_including_zero_kcal_placeholder() -> None:
    """Day rollups sum meal.total_calories; a pending/zero row is explicit (contract)."""
    from datetime import datetime
    from types import SimpleNamespace
    from zoneinfo import ZoneInfo

    from calorie_bot.app.services.stats_service import StatsService

    TZ = ZoneInfo("Europe/Moscow")

    def _meal(uid: int, at: datetime, kcal: int) -> SimpleNamespace:
        return SimpleNamespace(
            user_id=uid,
            eaten_at=at,
            total_calories=kcal,
            total_calories_min=None,
            total_calories_max=None,
            has_estimated_items=False,
            items=[SimpleNamespace(name="x", calories=kcal)],
        )

    meals = [
        _meal(1, datetime(2026, 5, 1, 8, 0, tzinfo=TZ), 400),
        _meal(1, datetime(2026, 5, 1, 13, 0, tzinfo=TZ), 300),
        _meal(1, datetime(2026, 5, 1, 16, 0, tzinfo=TZ), 0),
    ]

    class FakeRepo:
        def __init__(self, data: list) -> None:
            self._data = data

        async def list_confirmed_meals_between(self, user_id: int, start_at, end_at):
            return [m for m in self._data if getattr(m, "user_id", 1) == user_id]

    class FakeProf:
        async def get_by_user_id(self, user_id: int):
            return SimpleNamespace(daily_calorie_target=2000, timezone="Europe/Moscow")

    svc = StatsService(
        stats_repository=FakeRepo(meals),
        profile_repository=FakeProf(),
        default_timezone="Europe/Moscow",
        now_factory=lambda tz: datetime(2026, 5, 1, 20, 0, tzinfo=tz),
    )
    view = await svc.today_view(1)
    assert view.total_calories == 700
    assert view.meals_count == 3
