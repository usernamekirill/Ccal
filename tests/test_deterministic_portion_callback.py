"""Deterministic portion quick-pick routing (no text-meal AI on indexed callbacks)."""

from calorie_bot.app.ai.clarification_orchestrator import (
    build_llm_context,
    multi_item_missing_weight_clarification_body,
)
from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.handlers import meal_portion_pick as mpp
from calorie_bot.app.keyboards.meal import PortionQuickPickParsed, parse_quick_pick_grams_raw
from calorie_bot.app.services.calorie_service import CalorieService


def test_effective_indexed_pick_multi_item() -> None:
    p = parse_quick_pick_grams_raw("item=0:weight=120")
    assert mpp._effective_indexed_pick(p, 2) == p


def test_effective_indexed_pick_single_legacy_mpt() -> None:
    p = PortionQuickPickParsed("legacy", None, 120)
    eff = mpp._effective_indexed_pick(p, 1)
    assert eff is not None
    assert eff.kind == "indexed" and eff.item_index == 0 and eff.grams == 120


def test_effective_indexed_pick_legacy_multi_requires_ai() -> None:
    p = PortionQuickPickParsed("legacy", None, 120)
    assert mpp._effective_indexed_pick(p, 2) is None


def test_partial_multi_body_shows_remaining_only() -> None:
    svc = CalorieService()
    fr = FoodRecognitionResult(
        items=[
            FoodItemRecognition.model_validate(
                {
                    "name": "котлета",
                    "portion_description": "120 г",
                    "estimated_grams": 120.0,
                    "calories_per_100g": 200.0,
                    "protein_per_100g": 15.0,
                    "fat_per_100g": 10.0,
                    "carbs_per_100g": 0.0,
                    "calories": 240,
                }
            ),
            FoodItemRecognition.model_validate(
                {"name": "макароны", "portion_description": "порция", "estimated_grams": None, "calories": 0}
            ),
        ],
        total_calories=240,
        overall_confidence=0.85,
        comment="x",
    )
    fr = svc.validate_food_result(fr)
    ctx = build_llm_context(fr, svc)
    body = multi_item_missing_weight_clarification_body(ctx)
    assert body is not None
    assert "Осталось уточнить" in body
    assert "макароны" in body.lower()
