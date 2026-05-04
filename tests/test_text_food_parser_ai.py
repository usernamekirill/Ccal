"""Structured OpenAI text-food parser: mapping + pipeline with mocked LLM (no live API)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from pydantic import SecretStr

from calorie_bot.app.ai.nlp.text_food_parser import (
    StructuredTextMealResponse,
    structured_meal_to_food_result,
)
from calorie_bot.app.ai.text_parser_service import FoodTextParserService
from calorie_bot.app.config import Settings


def _stub_settings() -> Settings:
    return Settings(
        telegram_bot_token=SecretStr("t"),
        openai_api_key=SecretStr("test-key"),
        openai_timeout_seconds=30,
        openai_correction_model="gpt-test",
    )


def _meal_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _mock_openai_completion(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _base_item(
    *,
    name: str,
    canonical: str | None = None,
    weight: float | None,
    portion: str,
    per_c: float,
    per_p: float,
    per_f: float,
    per_cb: float,
    cal: int,
    p: float,
    f: float,
    c: float,
    qty: float = 1,
    unit: str = "g",
    clar: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "canonical_name": canonical or name,
        "quantity": qty,
        "unit": unit,
        "weight_grams": weight,
        "portion_description": portion,
        "calories_per_100g": per_c,
        "protein_per_100g": per_p,
        "fat_per_100g": per_f,
        "carbs_per_100g": per_cb,
        "calories": cal,
        "protein": p,
        "fat": f,
        "carbs": c,
        "confidence": 0.88,
        "is_estimated": clar,
    }


def _shell(**kwargs: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "recognized": True,
        "needs_clarification": False,
        "clarification_question": None,
        "meal_type": "unknown",
        "items": [],
        "totals": {"calories": 0, "protein": 0, "fat": 0, "carbs": 0},
        "user_message_normalized": "",
        "reasoning_summary": "test",
    }
    base.update(kwargs)
    return base


@pytest.mark.asyncio
async def test_pipeline_grechka_200g_mocked() -> None:
    raw = _shell(
        items=[
            _base_item(
                name="гречка",
                canonical="гречка",
                weight=200,
                portion="200 г",
                per_c=120,
                per_p=4.2,
                per_f=2.5,
                per_cb=24,
                cal=240,
                p=8.4,
                f=5.0,
                c=48,
            )
        ],
        totals={"calories": 240, "protein": 8.4, "fat": 5, "carbs": 48},
        user_message_normalized="гречка 200 г",
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_mock_openai_completion(_meal_json(raw)),
    )
    settings = _stub_settings()
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text(
        "гречка 200г",
        default_meal_type="lunch",
    )
    assert out.items
    assert out.items[0].name == "гречка"
    assert out.items[0].estimated_grams == 200
    assert out.needs_clarification is False


@pytest.mark.asyncio
async def test_pipeline_200g_grechki_word_order() -> None:
    raw = _shell(
        items=[
            _base_item(
                name="гречка",
                weight=200,
                portion="200 г",
                per_c=120,
                per_p=4.2,
                per_f=2.5,
                per_cb=24,
                cal=240,
                p=8.4,
                f=5.0,
                c=48,
            )
        ],
        user_message_normalized="200 г гречки",
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_mock_openai_completion(_meal_json(raw)),
    )
    settings = _stub_settings()
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text("200 г гречки")
    assert out.items[0].name == "гречка"
    assert out.items[0].estimated_grams == 200


@pytest.mark.asyncio
async def test_pipeline_sharlotka_piece_100g() -> None:
    raw = _shell(
        items=[
            _base_item(
                name="шарлотка",
                weight=100,
                portion="кусок",
                per_c=190,
                per_p=3,
                per_f=6,
                per_cb=32,
                cal=190,
                p=3,
                f=6,
                c=32,
            )
        ],
        needs_clarification=False,
        totals={"calories": 190, "protein": 3, "fat": 6, "carbs": 32},
        user_message_normalized="шарлотка 100 г",
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_mock_openai_completion(_meal_json(raw)),
    )
    settings = _stub_settings()
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text(
        "кусок пирога шарлотка 100 грамм",
    )
    assert out.items[0].name == "шарлотка"
    assert "кусок" in out.items[0].portion_description.lower()
    assert out.items[0].estimated_grams == 100
    assert out.needs_clarification is False


@pytest.mark.asyncio
async def test_pipeline_sharlotka_needs_weight() -> None:
    raw = _shell(
        items=[
            _base_item(
                name="шарлотка",
                weight=None,
                portion="кусок",
                per_c=190,
                per_p=3,
                per_f=6,
                per_cb=32,
                cal=0,
                p=0,
                f=0,
                c=0,
                clar=True,
            )
        ],
        needs_clarification=True,
        clarification_question="Вес не указан — укажите массу порции в граммах.",
        totals={"calories": 0, "protein": 0, "fat": 0, "carbs": 0},
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_mock_openai_completion(_meal_json(raw)),
    )
    settings = _stub_settings()
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text(
        "кусок пирога шарлотка",
    )
    assert out.items
    assert out.items[0].name == "шарлотка"
    assert out.needs_clarification is True
    assert out.clarification_question


@pytest.mark.asyncio
async def test_pipeline_apple_piece_or_clarify() -> None:
    raw = _shell(
        items=[
            _base_item(
                name="яблоко",
                weight=136,
                portion="1 шт",
                per_c=52,
                per_p=0.3,
                per_f=0.2,
                per_cb=14,
                cal=71,
                p=0.4,
                f=0.3,
                c=19,
                qty=1,
                unit="piece",
            )
        ],
        needs_clarification=False,
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_mock_openai_completion(_meal_json(raw)),
    )
    settings = _stub_settings()
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text("яблоко")
    assert out.items[0].name == "яблоко"


@pytest.mark.asyncio
async def test_pipeline_three_eggs_grams() -> None:
    raw = _shell(
        items=[
            _base_item(
                name="яйцо",
                weight=150,
                portion="3 шт",
                per_c=140,
                per_p=13,
                per_f=10,
                per_cb=1,
                cal=210,
                p=19.5,
                f=15,
                c=1.5,
                qty=3,
                unit="piece",
            )
        ],
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_mock_openai_completion(_meal_json(raw)),
    )
    settings = _stub_settings()
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text("три яйца")
    assert out.items[0].quantity == 3
    assert out.items[0].estimated_grams == 150


@pytest.mark.asyncio
async def test_pipeline_coffee_milk_sugar_three_items() -> None:
    raw = _shell(
        items=[
            _base_item(
                name="кофе",
                weight=200,
                portion="чашка",
                per_c=2,
                per_p=0.1,
                per_f=0,
                per_cb=0.3,
                cal=4,
                p=0.2,
                f=0,
                c=0.6,
            ),
            _base_item(
                name="молоко",
                weight=30,
                portion="в кофе",
                per_c=64,
                per_p=3.2,
                per_f=3.6,
                per_cb=4.8,
                cal=19,
                p=1,
                f=1.1,
                c=1.4,
            ),
            _base_item(
                name="сахар",
                weight=5,
                portion="ложка",
                per_c=400,
                per_p=0,
                per_f=0,
                per_cb=100,
                cal=20,
                p=0,
                f=0,
                c=5,
            ),
        ],
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_mock_openai_completion(_meal_json(raw)),
    )
    settings = _stub_settings()
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text(
        "кофе с молоком и сахаром",
    )
    assert len(out.items) == 3


@pytest.mark.asyncio
async def test_pipeline_blins_sour_cream_two_items() -> None:
    raw = _shell(
        items=[
            _base_item(
                name="блины",
                weight=150,
                portion="порция",
                per_c=200,
                per_p=6,
                per_f=8,
                per_cb=28,
                cal=300,
                p=9,
                f=12,
                c=42,
            ),
            _base_item(
                name="сметана",
                weight=40,
                portion="соус",
                per_c=193,
                per_p=2.8,
                per_f=20,
                per_cb=3.2,
                cal=77,
                p=1.1,
                f=8,
                c=1.3,
            ),
        ],
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_mock_openai_completion(_meal_json(raw)),
    )
    settings = _stub_settings()
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text("блины со сметаной")
    assert len(out.items) == 2


def test_wrong_totals_reconciled_from_items() -> None:
    """Server sums item calories; corrupt LLM totals field must not win."""
    data = StructuredTextMealResponse.model_validate(
        _shell(
            items=[
                _base_item(
                    name="а",
                    weight=100,
                    portion="100 г",
                    per_c=100,
                    per_p=25,
                    per_f=0,
                    per_cb=0,
                    cal=100,
                    p=25,
                    f=0,
                    c=0,
                ),
                _base_item(
                    name="б",
                    weight=100,
                    portion="100 г",
                    per_c=100,
                    per_p=25,
                    per_f=0,
                    per_cb=0,
                    cal=100,
                    p=25,
                    f=0,
                    c=0,
                ),
            ],
            totals={"calories": 9999, "protein": 1, "fat": 1, "carbs": 1},
        ),
    )
    out = structured_meal_to_food_result(data, user_text="x", default_meal_type=None)
    assert out.total_calories == 200


@pytest.mark.asyncio
async def test_invalid_json_falls_back_offline() -> None:
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_openai_completion("not-json {"))
    settings = _stub_settings()
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text("гречка 200 г")
    assert out.items
    assert out.items[0].name == "гречка"
    assert out.items[0].estimated_grams == 200


@pytest.mark.asyncio
async def test_invalid_json_and_offline_fail_returns_empty() -> None:
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_openai_completion("not-json {"))
    settings = _stub_settings()
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text("$$$")
    assert not out.items


@pytest.mark.asyncio
async def test_pie_generic_clarification() -> None:
    raw = _shell(
        recognized=True,
        items=[],
        needs_clarification=True,
        clarification_question="Уточните, какой пирог и примерный вес.",
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_mock_openai_completion(_meal_json(raw)),
    )
    settings = _stub_settings()
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text("пирог")
    assert not out.items
    assert out.needs_clarification
    assert "пирог" in (out.clarification_question or "").lower() or "уточн" in (out.clarification_question or "").lower()
