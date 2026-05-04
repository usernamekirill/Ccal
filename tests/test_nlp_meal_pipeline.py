"""NLP preprocessing and offline plaintext meal line (no OpenAI)."""

from __future__ import annotations

from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.nlp.meal_text_preprocess import (
    canonicalize_food_phrase,
    normalize_meal_input_text,
    try_bare_number_after_food,
    try_grams_only_clarification,
    try_parse_plaintext_meal_line,
)
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.services.food_parser_service import extract_ordered_gram_values


def test_normalize_glued_digits_and_spaces() -> None:
    # «200» и «г» разделяются для стабильного gram-token (дальше «г» — отдельное слово)
    assert normalize_meal_input_text("гречка200г") == "гречка 200 г"
    assert normalize_meal_input_text("гречка   200   г") == "гречка 200 г"


def test_acceptance_examples_weights_and_names() -> None:
    """Спек: гречка 200г; 150 грамм; 170 грамм шарлотки → шарлотка; 200 г риса; курицы 180г."""
    r1 = try_parse_plaintext_meal_line(normalize_meal_input_text("гречка 200г"))
    assert r1 and r1.items[0].estimated_grams == 200.0

    r2 = try_parse_plaintext_meal_line(normalize_meal_input_text("гречка 150 грамм"))
    assert r2 and r2.items[0].estimated_grams == 150.0

    r3 = try_parse_plaintext_meal_line(normalize_meal_input_text("170 грамм шарлотки"))
    assert r3 and r3.items[0].estimated_grams == 170.0
    assert "шарлот" in r3.items[0].name.lower()

    r4 = try_parse_plaintext_meal_line(normalize_meal_input_text("200 г риса"))
    assert r4 and r4.items[0].estimated_grams == 200.0
    assert r4.items[0].name == "рис"

    r5 = try_parse_plaintext_meal_line(normalize_meal_input_text("курицы 180г"))
    assert r5 and r5.items[0].estimated_grams == 180.0
    assert r5.items[0].name == "курица"


def test_canonicalize_inflect_forms() -> None:
    assert canonicalize_food_phrase("гречки") == "гречка"
    assert canonicalize_food_phrase("шарлотки") == "шарлотка"


def test_grams_only_triggers_clarification() -> None:
    q = try_grams_only_clarification("200 г")
    assert q is not None
    assert q.needs_clarification is True
    assert not q.items


def test_bare_number_triggers_clarification_not_fail() -> None:
    q = try_bare_number_after_food("гречка 200")
    assert q is not None
    assert q.needs_clarification is True
    assert q.items and q.clarification_question and "грамм" in q.clarification_question.lower()


def test_extract_ordered_after_normalize() -> None:
    assert extract_ordered_gram_values(normalize_meal_input_text("гречка200г")) == [200.0]


def test_multi_item_phrase_not_split_offline() -> None:
    """Несколько продуктов без LLM не режутся — ожидается модель (документация поведения)."""
    assert try_parse_plaintext_meal_line(normalize_meal_input_text("5 блинов со сметаной")) is None


def test_validate_total_equals_sum_line_calories() -> None:
    """После validate сумма строк = total_calories для точечной массы (из спека §12)."""
    svc = CalorieService()
    base = try_parse_plaintext_meal_line("гречка 100 г")
    assert base is not None
    merged = FoodRecognitionResult.model_validate(
        {
            **base.model_dump(),
            "items": [
                base.items[0].model_copy(
                    update={
                        "calories": 120,
                        "calories_per_100g": 120.0,
                        "protein": 4.0,
                        "fat": 2.0,
                        "carbs": 22.0,
                    }
                ),
                base.items[0].model_copy(
                    update={
                        "name": "курица",
                        "calories": 165,
                        "calories_per_100g": 165.0,
                        "protein": 31.0,
                        "fat": 4.0,
                        "carbs": 0.0,
                        "estimated_grams": 100.0,
                        "portion_description": "100 г",
                    }
                ),
            ],
        }
    )
    out = svc.validate_food_result(merged)
    assert len(out.items) == 2
    assert out.total_calories == out.items[0].calories + out.items[1].calories
