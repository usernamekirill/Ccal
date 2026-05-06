"""Clarification orchestrator: priority, context-aware presets, no validator dump."""

from calorie_bot.app.ai.clarification_orchestrator import (
    build_dish_line,
    build_llm_context,
    classify_primary_issue,
    portion_presets_for_dish,
)
from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.services.calorie_service import CalorieService


def _item(name: str, *, grams: float | None = 200.0) -> FoodItemRecognition:
    return FoodItemRecognition.model_validate(
        {
            "name": name,
            "portion_description": "порция",
            "estimated_grams": grams,
            "calories": 100,
        }
    )


def test_case1_tvorog_med_only_missing_weight_priority() -> None:
    """CASE 1: recognizable dish, only mass missing — primary issue is missing_weight."""
    svc = CalorieService()
    r = FoodRecognitionResult(
        items=[
            _item("творог", grams=None),
            _item("мёд", grams=None),
        ],
        total_calories=0,
        overall_confidence=0.85,
        comment="x",
        needs_clarification=True,
    )
    r = svc.validate_food_result(r)
    r = svc.apply_clarification_guards(r)
    assert classify_primary_issue(r, svc) == "missing_weight"
    grams_labels = [g for g, _ in portion_presets_for_dish("творог с мёдом")]
    assert 150 in grams_labels and 300 in grams_labels
    q = (r.clarification_question or "").lower()
    assert "пармезан" not in q
    assert "макарон" not in q
    assert "оценка неточная" not in q


def test_case3_sharlotka_presets() -> None:
    """CASE 3: cake-like dish gets slice-oriented gram hints."""
    presets = portion_presets_for_dish("шарлотка")
    assert presets[0][0] in (80, 100)


def test_case4_soup_presets() -> None:
    """CASE 4: soup gets bowl-oriented portions."""
    presets = portion_presets_for_dish("суп")
    assert any(g >= 250 for g, _ in presets)


def test_case5_pasta_no_dairy_presets() -> None:
    """CASE 5: pasta context must not use cottage-cheese-specific copy in presets."""
    presets = portion_presets_for_dish("макароны с сыром")
    assert presets[0][0] == 200
    dish, _ = build_dish_line(
        FoodRecognitionResult(
            items=[_item("макароны"), _item("сыр")],
            total_calories=0,
            overall_confidence=0.9,
            comment="x",
        )
    )
    assert "творог" not in dish.lower()


def test_llm_context_single_primary_issue() -> None:
    """Orchestrator exposes one primary_issue for the clarification model."""
    svc = CalorieService()
    r = FoodRecognitionResult(
        items=[_item("творог", grams=None)],
        total_calories=0,
        overall_confidence=0.4,
        comment="x",
    )
    r = svc.validate_food_result(r)
    r = svc.apply_clarification_guards(r)
    ctx = build_llm_context(r, svc)
    assert ctx.primary_issue == "missing_weight"
    assert "grams" in ctx.missing_fields
