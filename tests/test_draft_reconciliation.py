"""Draft reconciliation validation and mocked CASE 1–5 (no live OpenAI)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from calorie_bot.app.ai.nlp.draft_reconciliation import (
    apply_reconciliation_validators,
    salient_terms_from_user_text,
)
from calorie_bot.app.ai.text_parser_service import FoodTextParserService
from calorie_bot.app.config import Settings
from calorie_bot.app.services.calorie_service import CalorieService


def _settings() -> Settings:
    return Settings(
        telegram_bot_token=SecretStr("t"),
        openai_api_key=SecretStr("k"),
        openai_timeout_seconds=30,
        openai_correction_model="gpt-test",
    )


def _mock_completion(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    ch = MagicMock()
    ch.message = msg
    r = MagicMock()
    r.choices = [ch]
    return r


def _item(
    *,
    name: str,
    weight: float | None,
    portion: str,
    cal: int,
    p: float,
    f: float,
    c: float,
    per_c: float,
    qty: float = 1.0,
    unit: str = "g",
    user_mass: bool = True,
) -> dict[str, Any]:
    return {
        "name": name,
        "canonical_name": name,
        "quantity": qty,
        "unit": unit,
        "weight_grams": weight,
        "user_stated_mass": user_mass,
        "portion_description": portion,
        "calories_per_100g": per_c,
        "protein_per_100g": 20.0,
        "fat_per_100g": 5.0,
        "carbs_per_100g": 0.0,
        "calories": cal,
        "protein": p,
        "fat": f,
        "carbs": c,
        "confidence": 0.88,
        "is_estimated": False,
    }


def _response_payload(**kwargs: Any) -> str:
    base: dict[str, Any] = {
        "recognized": True,
        "intent": "update",
        "mode": "update",
        "needs_clarification": False,
        "clarification_question": None,
        "clarification_questions": [],
        "clarification_options": [],
        "user_named_products": [],
        "removed_items": [],
        "updated_items": [],
        "meal_type": "lunch",
        "items": [],
        "totals": {"calories": 0, "protein": 0, "fat": 0, "carbs": 0},
        "user_message_normalized": "",
        "reasoning_summary": "test",
    }
    base.update(kwargs)
    return json.dumps(base, ensure_ascii=False)


@pytest.mark.asyncio
async def test_case1_turkey_replaces_chicken_from_photo_context() -> None:
    out_items = [
        _item(
            name="индейка с сыром",
            weight=None,
            portion="2 порции",
            cal=0,
            p=0,
            f=0,
            c=0,
            per_c=120,
            qty=2,
            unit="piece",
            user_mass=False,
        )
    ]
    raw = _response_payload(
        items=out_items,
        user_named_products=["индейка", "сыр"],
        user_message_normalized="индейка с сыром две порции",
        intent="overwrite",
        updated_items=["индейка с сыром"],
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_completion(raw))
    cs = CalorieService()
    vision = cs.validate_food_result(
        cs.result_from_dict(
            {
                "items": [
                    {
                        "name": "курица",
                        "portion_description": "100 г",
                        "estimated_grams": 100,
                        "calories": 165,
                        "protein": 31,
                        "fat": 4,
                        "carbs": 0,
                        "food_confidence": 0.8,
                        "portion_confidence": 0.8,
                        "grams_source": "ai_photo",
                    }
                ],
                "total_calories": 165,
                "overall_confidence": 0.8,
                "comment": "v",
            }
        )
    )
    draft_dict = cs.result_to_dict(vision)
    result = await FoodTextParserService(_settings(), openai_client=client).parse_food_text(
        "индейка с сыром две порции",
        default_meal_type="lunch",
        context={
            "current_draft": draft_dict,
            "vision_baseline": draft_dict,
        },
    )
    assert len(result.items) == 1
    assert "индейка" in result.items[0].name.lower()
    assert "курица" not in " ".join(i.name.lower() for i in result.items)


@pytest.mark.asyncio
async def test_case2_two_pcs_applies_to_existing_not_new_random_item() -> None:
    current_items = [
        _item(
            name="индейка с сыром",
            weight=None,
            portion="порция",
            cal=0,
            p=0,
            f=0,
            c=0,
            per_c=110,
            qty=2,
            unit="piece",
            user_mass=False,
        )
    ]
    raw = _response_payload(
        items=current_items,
        user_named_products=[],
        intent="update",
        user_message_normalized="2 шт",
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_completion(raw))
    cs = CalorieService()
    cur = cs.result_from_dict(
        {
            "items": [
                {
                    "name": "индейка с сыром",
                    "portion_description": "порция",
                    "estimated_grams": None,
                    "calories": 0,
                    "protein": 0,
                    "fat": 0,
                    "carbs": 0,
                    "calories_per_100g": 110,
                    "protein_per_100g": 20,
                    "fat_per_100g": 5,
                    "carbs_per_100g": 0,
                    "food_confidence": 0.8,
                    "portion_confidence": 0.5,
                    "grams_source": "unknown",
                    "quantity": 1,
                    "unit_type": "piece",
                }
            ],
            "total_calories": 0,
            "overall_confidence": 0.8,
            "comment": "x",
        }
    )
    dd = cs.result_to_dict(cur)
    result = await FoodTextParserService(_settings(), openai_client=client).parse_food_text(
        "2 шт",
        context={"current_draft": dd},
    )
    assert len(result.items) == 1
    assert result.items[0].quantity == 2


@pytest.mark.asyncio
async def test_case3_three_item_meal_preserved() -> None:
    items = [
        _item(name="суп из чечевицы", weight=250, portion="тарелка", cal=180, p=10, f=4, c=22, per_c=72),
        _item(name="пюре", weight=150, portion="гарнир", cal=120, p=2, f=5, c=18, per_c=80),
        _item(name="индейка", weight=80, portion="2 куска", cal=140, p=25, f=4, c=0, per_c=175, qty=2, unit="piece"),
    ]
    raw = _response_payload(
        items=items,
        user_named_products=["чечевица", "пюре", "индейка"],
        intent="create",
        mode="create",
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_completion(raw))
    result = await FoodTextParserService(_settings(), openai_client=client).parse_food_text(
        "суп из чечевицы и пюре с двумя кусками индейки",
    )
    assert len(result.items) == 3
    names = " ".join(i.name.lower() for i in result.items)
    assert "чечевиц" in names or "суп" in names
    assert "пюре" in names
    assert "индейка" in names


@pytest.mark.asyncio
async def test_case4_negation_overwrite_turkey() -> None:
    items = [
        _item(name="индейка", weight=120, portion="120 г", cal=200, p=35, f=5, c=0, per_c=167),
    ]
    raw = _response_payload(
        items=items,
        user_named_products=["индейка"],
        intent="overwrite",
        updated_items=["индейка"],
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_completion(raw))
    cs = CalorieService()
    cur = cs.result_from_dict(
        {
            "items": [
                {
                    "name": "курица",
                    "portion_description": "120 г",
                    "estimated_grams": 120,
                    "calories": 200,
                    "protein": 35,
                    "fat": 5,
                    "carbs": 0,
                    "calories_per_100g": 167,
                    "protein_per_100g": 27,
                    "fat_per_100g": 8,
                    "carbs_per_100g": 0,
                    "food_confidence": 0.8,
                    "portion_confidence": 0.8,
                    "grams_source": "ai_photo",
                }
            ],
            "total_calories": 200,
            "overall_confidence": 0.8,
            "comment": "x",
        }
    )
    result = await FoodTextParserService(_settings(), openai_client=client).parse_food_text(
        "не курица, а индейка",
        context={"current_draft": cs.result_to_dict(cur)},
    )
    assert "индейка" in result.items[0].name.lower()


@pytest.mark.asyncio
async def test_case5_remove_soup_keep_rest() -> None:
    items = [
        _item(name="пюре", weight=150, portion="150 г", cal=120, p=2, f=5, c=18, per_c=80),
        _item(name="индейка", weight=100, portion="100 г", cal=175, p=28, f=4, c=0, per_c=175),
    ]
    raw = _response_payload(
        items=items,
        user_named_products=[],
        removed_items=["суп из чечевицы"],
        intent="remove",
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_completion(raw))
    cs = CalorieService()
    three = cs.result_from_dict(
        {
            "items": [
                {
                    "name": "суп из чечевицы",
                    "portion_description": "250 г",
                    "estimated_grams": 250,
                    "calories": 180,
                    "protein": 10,
                    "fat": 4,
                    "carbs": 22,
                    "calories_per_100g": 72,
                    "food_confidence": 0.8,
                    "portion_confidence": 0.8,
                    "grams_source": "ai_photo",
                },
                {
                    "name": "пюре",
                    "portion_description": "150 г",
                    "estimated_grams": 150,
                    "calories": 120,
                    "protein": 2,
                    "fat": 5,
                    "carbs": 18,
                    "calories_per_100g": 80,
                    "food_confidence": 0.8,
                    "portion_confidence": 0.8,
                    "grams_source": "ai_photo",
                },
                {
                    "name": "индейка",
                    "portion_description": "100 г",
                    "estimated_grams": 100,
                    "calories": 175,
                    "protein": 28,
                    "fat": 4,
                    "carbs": 0,
                    "calories_per_100g": 175,
                    "food_confidence": 0.8,
                    "portion_confidence": 0.8,
                    "grams_source": "ai_photo",
                },
            ],
            "total_calories": 475,
            "overall_confidence": 0.8,
            "comment": "x",
        }
    )
    result = await FoodTextParserService(_settings(), openai_client=client).parse_food_text(
        "убери суп",
        context={"current_draft": cs.result_to_dict(three)},
    )
    assert len(result.items) == 2
    assert all("суп" not in i.name.lower() and "чечевиц" not in i.name.lower() for i in result.items)


def test_entity_mismatch_triggers_clarification() -> None:
    cs = CalorieService()
    fr = cs.validate_food_result(
        cs.result_from_dict(
            {
                "items": [
                    {
                        "name": "курица",
                        "portion_description": "150 г",
                        "estimated_grams": 150,
                        "calories": 250,
                        "protein": 40,
                        "fat": 8,
                        "carbs": 0,
                        "calories_per_100g": 167,
                        "food_confidence": 0.8,
                        "portion_confidence": 0.8,
                        "grams_source": "ai_photo",
                    }
                ],
                "total_calories": 250,
                "overall_confidence": 0.8,
                "comment": "x",
            }
        )
    )
    out = apply_reconciliation_validators(
        user_message_raw="индейка",
        user_message_normalized="индейка",
        calorie_service=cs,
        structured_user_named_products=["индейка"],
        fr=fr,
    )
    assert out.needs_clarification


def test_salient_tokens_not_empty_for_multicomponent_phrase() -> None:
    t = salient_terms_from_user_text("суп из чечевицы и пюре с индейкой")
    assert "чечевицы" in t or "чечевиц" in " ".join(t)