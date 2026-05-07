"""Portion clarification: multi-ingredient labels, clarify_weight callbacks, synthetic text."""

from calorie_bot.app.ai.clarification_orchestrator import missing_weight_portion_actions
from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.domain import GramsSource
from calorie_bot.app.keyboards.meal import (
    CLARIFY_WEIGHT_PREFIX,
    PORTION_CUSTOM_FREE_TEXT_HINT,
    PORTION_QUICK_PICK_CUSTOM_LABEL,
    contextual_portion_keyboard,
    format_multi_item_portion_button_label,
    format_single_item_portion_button_label,
    parse_quick_pick_grams_raw,
    portion_pick_synthetic_user_text,
)
from calorie_bot.app.services.calorie_service import CalorieService


def test_case1_multi_item_dish_buttons_tvorog_med() -> None:
    """No shared «творога и мёда» weight; item-scoped labels and clarify_weight callbacks."""
    r = FoodRecognitionResult(
        items=[
            FoodItemRecognition.model_validate(
                {"name": "творог", "portion_description": "порция", "estimated_grams": None, "calories": 0}
            ),
            FoodItemRecognition.model_validate(
                {"name": "мёд", "portion_description": "порция", "estimated_grams": None, "calories": 0}
            ),
        ],
        total_calories=0,
        overall_confidence=0.85,
        comment="x",
    )
    actions = missing_weight_portion_actions(r)
    kb = contextual_portion_keyboard(actions, single_ingredient_clarification=False)
    flat = [b for row in kb.inline_keyboard for b in row]
    texts = [(b.text or "") for b in flat]
    cbs = [(b.callback_data or "") for b in flat]

    assert any("🥣 Творог 150 г" == t for t in texts)
    assert any("🥣 Творог 200 г" == t for t in texts)
    assert any("🍯 Мёд 20 г" == t for t in texts)
    assert any("🍯 Мёд 30 г" == t for t in texts)
    assert PORTION_QUICK_PICK_CUSTOM_LABEL in texts

    joined = " ".join(texts + cbs).lower()
    assert "творога и меда" not in joined
    assert "100 г творога и меда" not in joined
    assert any(":item=0:weight=" in cb for cb in cbs)
    assert any(":item=1:weight=" in cb for cb in cbs)
    assert any(cb == f"{CLARIFY_WEIGHT_PREFIX}:x" for cb in cbs)


def test_case2_single_item_buttons_plain_grams() -> None:
    r = FoodRecognitionResult(
        items=[
            FoodItemRecognition.model_validate(
                {
                    "name": "шарлотка",
                    "portion_description": "порция",
                    "estimated_grams": None,
                    "calories": 0,
                }
            ),
        ],
        total_calories=0,
        overall_confidence=0.85,
        comment="x",
    )
    actions = missing_weight_portion_actions(r)
    kb = contextual_portion_keyboard(actions, single_ingredient_clarification=True)
    flat = [b for row in kb.inline_keyboard for b in row]
    texts = [b.text for b in flat if b.text]
    assert texts[:3] == ["100 г", "150 г", "200 г"]
    assert flat[-1].callback_data == "mpt:x"
    assert all(
        (b.callback_data or "").startswith("mpt:") and "clarify" not in (b.callback_data or "")
        for b in flat[:-1]
    )


def test_case3_compact_indexed_still_parses() -> None:
    v = parse_quick_pick_grams_raw("item_index=0:weight=150")
    c = parse_quick_pick_grams_raw("0:150")
    w = parse_quick_pick_grams_raw("item=0:weight=150")
    assert v == c == w
    assert v.kind == "indexed" and v.item_index == 0 and v.grams == 150


def test_case3_update_grams_only_first_item() -> None:
    svc = CalorieService()
    fr = FoodRecognitionResult(
        items=[
            FoodItemRecognition.model_validate(
                {
                    "name": "творог",
                    "portion_description": "порция",
                    "estimated_grams": None,
                    "calories_per_100g": 100.0,
                    "protein_per_100g": 10.0,
                    "fat_per_100g": 5.0,
                    "carbs_per_100g": 10.0,
                    "calories": 0,
                }
            ),
            FoodItemRecognition.model_validate(
                {
                    "name": "мёд",
                    "portion_description": "порция",
                    "estimated_grams": None,
                    "calories_per_100g": 300.0,
                    "protein_per_100g": 0.0,
                    "fat_per_100g": 0.0,
                    "carbs_per_100g": 80.0,
                    "calories": 0,
                }
            ),
        ],
        total_calories=0,
        overall_confidence=0.85,
        comment="x",
    )
    fr = svc.validate_food_result(fr)
    out = svc.update_grams(fr, 1, 150.0, grams_source=GramsSource.USER.value)
    assert out.items[0].estimated_grams == 150.0
    assert out.items[1].estimated_grams is None


def test_case4_update_only_second_item_invariant() -> None:
    """Models expected merge outcome for «мёд 20 г» (LLM path; invariant via update_grams)."""
    svc = CalorieService()
    fr = FoodRecognitionResult(
        items=[
            FoodItemRecognition.model_validate(
                {
                    "name": "творог",
                    "portion_description": "порция",
                    "estimated_grams": None,
                    "calories_per_100g": 100.0,
                    "protein_per_100g": 10.0,
                    "fat_per_100g": 5.0,
                    "carbs_per_100g": 10.0,
                    "calories": 0,
                }
            ),
            FoodItemRecognition.model_validate(
                {
                    "name": "мёд",
                    "portion_description": "порция",
                    "estimated_grams": None,
                    "calories_per_100g": 300.0,
                    "protein_per_100g": 0.0,
                    "fat_per_100g": 0.0,
                    "carbs_per_100g": 80.0,
                    "calories": 0,
                }
            ),
        ],
        total_calories=0,
        overall_confidence=0.85,
        comment="x",
    )
    fr = svc.validate_food_result(fr)
    out = svc.update_grams(fr, 2, 20.0, grams_source=GramsSource.USER.value)
    assert out.items[0].estimated_grams is None
    assert out.items[1].estimated_grams == 20.0


def test_case5_update_both_items_sequential_invariant() -> None:
    svc = CalorieService()
    fr = FoodRecognitionResult(
        items=[
            FoodItemRecognition.model_validate(
                {
                    "name": "творог",
                    "portion_description": "порция",
                    "estimated_grams": None,
                    "calories_per_100g": 100.0,
                    "protein_per_100g": 10.0,
                    "fat_per_100g": 5.0,
                    "carbs_per_100g": 10.0,
                    "calories": 0,
                }
            ),
            FoodItemRecognition.model_validate(
                {
                    "name": "мёд",
                    "portion_description": "порция",
                    "estimated_grams": None,
                    "calories_per_100g": 300.0,
                    "protein_per_100g": 0.0,
                    "fat_per_100g": 0.0,
                    "carbs_per_100g": 80.0,
                    "calories": 0,
                }
            ),
        ],
        total_calories=0,
        overall_confidence=0.85,
        comment="x",
    )
    fr = svc.validate_food_result(fr)
    out = svc.update_grams(fr, 1, 180.0, grams_source=GramsSource.USER.value)
    out = svc.update_grams(out, 2, 20.0, grams_source=GramsSource.USER.value)
    assert out.items[0].estimated_grams == 180.0
    assert out.items[1].estimated_grams == 20.0


def test_multi_label_format_no_middle_dot() -> None:
    assert format_multi_item_portion_button_label("творог", 100) == "🥣 Творог 100 г"
    assert format_multi_item_portion_button_label("мёд", 30) == "🍯 Мёд 30 г"


def test_single_label_plain() -> None:
    assert format_single_item_portion_button_label(100) == "100 г"


def test_synthetic_from_clarify_weight_indexed() -> None:
    fr = FoodRecognitionResult(
        items=[
            FoodItemRecognition.model_validate(
                {"name": "творог", "portion_description": "порция", "estimated_grams": None, "calories": 0}
            ),
            FoodItemRecognition.model_validate(
                {"name": "мёд", "portion_description": "порция", "estimated_grams": None, "calories": 0}
            ),
        ],
        total_calories=0,
        overall_confidence=0.85,
        comment="x",
    )
    p = parse_quick_pick_grams_raw("1:20")
    assert portion_pick_synthetic_user_text(fr, p) == "мёд 20 г"


def test_hint_lists_combined_phrase_example() -> None:
    assert "творог 180 г, мёд 20 г" in PORTION_CUSTOM_FREE_TEXT_HINT
