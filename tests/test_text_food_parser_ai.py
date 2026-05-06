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
from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.ai.text_parser_service import FoodTextParserService
from calorie_bot.app.config import Settings
from calorie_bot.app.services.calorie_service import CalorieService


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
    user_stated_mass: bool | None = None,
) -> dict[str, Any]:
    stated = user_stated_mass if user_stated_mass is not None else (weight is not None)
    return {
        "name": name,
        "canonical_name": canonical or name,
        "quantity": qty,
        "unit": unit,
        "weight_grams": weight,
        "user_stated_mass": stated,
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
        "mode": "create",
        "needs_clarification": False,
        "clarification_question": None,
        "clarification_options": [],
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
async def test_invalid_json_returns_clarification_not_offline_parse() -> None:
    """Without plaintext fallback, bad model JSON becomes a soft clarification result."""
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_openai_completion("not-json {"))
    settings = _stub_settings()
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text("гречка 200 г")
    assert not out.items
    assert out.needs_clarification
    assert out.clarification_question


@pytest.mark.asyncio
async def test_invalid_json_and_nonsense_returns_clarification() -> None:
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_openai_completion("not-json {"))
    settings = _stub_settings()
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text("$$$")
    assert not out.items
    assert out.needs_clarification


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


@pytest.mark.asyncio
async def test_grechka_without_weight_requests_clarification() -> None:
    raw = _shell(
        items=[
            _base_item(
                name="гречка",
                weight=None,
                portion="порция",
                per_c=120,
                per_p=4,
                per_f=2,
                per_cb=24,
                cal=0,
                p=0,
                f=0,
                c=0,
                clar=True,
                user_stated_mass=False,
            )
        ],
        needs_clarification=True,
        clarification_question="Укажите вес гречки.",
        clarification_options=["100 г", "150 г", "200 г"],
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_openai_completion(_meal_json(raw)))
    settings = _stub_settings()
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text("гречка")
    assert out.items and out.items[0].name == "гречка"
    assert out.needs_clarification
    assert "100" in (out.clarification_question or "")


@pytest.mark.asyncio
async def test_update_context_sent_to_openai_and_merges_chicken() -> None:
    settings = _stub_settings()
    raw = _shell(
        mode="update",
        items=[
            _base_item(
                name="гречка",
                weight=200,
                portion="200 г",
                per_c=120,
                per_p=4,
                per_f=2,
                per_cb=24,
                cal=240,
                p=8,
                f=4,
                c=48,
            ),
            _base_item(
                name="курица",
                weight=200,
                portion="200 г",
                per_c=165,
                per_p=31,
                per_f=4,
                per_cb=0,
                cal=330,
                p=62,
                f=8,
                c=0,
            ),
        ],
    )
    envelope: dict[str, Any] = {}

    async def _capture(**kwargs: Any):
        envelope.clear()
        envelope.update(json.loads(kwargs["messages"][1]["content"]))
        return _mock_openai_completion(_meal_json(raw))

    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=_capture)
    cs = CalorieService()
    draft = cs.result_to_dict(
        cs.validate_food_result(
            FoodRecognitionResult(
                items=[
                    FoodItemRecognition(
                        name="гречка",
                        portion_description="200 г",
                        estimated_grams=200,
                        calories=240,
                        protein=13.0,
                        fat=8.0,
                        carbs=52.0,
                        calories_per_100g=120,
                        protein_per_100g=6.5,
                        fat_per_100g=4,
                        carbs_per_100g=26,
                    ),
                    FoodItemRecognition(
                        name="курица",
                        portion_description="150 г",
                        estimated_grams=150,
                        calories=250,
                        protein=40.0,
                        fat=12.0,
                        carbs=0.0,
                        calories_per_100g=167,
                        protein_per_100g=27,
                        fat_per_100g=8,
                        carbs_per_100g=0,
                    ),
                ],
                total_calories=490,
                overall_confidence=0.9,
                comment="t",
            )
        )
    )
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text(
        "курица 200 г",
        default_meal_type="lunch",
        context={"current_draft": draft},
    )
    assert envelope.get("conversation_mode") == "update"
    assert envelope.get("current_draft") is not None
    assert len(envelope["current_draft"]["items"]) == 2
    assert len(out.items) == 2
    chicken = next(i for i in out.items if i.name == "курица")
    assert chicken.estimated_grams == 200


@pytest.mark.asyncio
async def test_remove_item_via_context() -> None:
    raw = _shell(
        mode="update",
        items=[
            _base_item(
                name="гречка",
                weight=200,
                portion="200 г",
                per_c=120,
                per_p=4,
                per_f=2,
                per_cb=24,
                cal=240,
                p=8,
                f=4,
                c=48,
            ),
        ],
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_openai_completion(_meal_json(raw)))
    settings = _stub_settings()
    cs = CalorieService()
    draft = cs.result_to_dict(
        cs.validate_food_result(
            FoodRecognitionResult(
                items=[
                    FoodItemRecognition(
                        name="гречка",
                        portion_description="200 г",
                        estimated_grams=200,
                        calories=240,
                        protein=8,
                        fat=4,
                        carbs=48,
                        calories_per_100g=120,
                        protein_per_100g=4,
                        fat_per_100g=2,
                        carbs_per_100g=24,
                    ),
                    FoodItemRecognition(
                        name="курица",
                        portion_description="150 г",
                        estimated_grams=150,
                        calories=250,
                        protein=40,
                        fat=8,
                        carbs=0,
                        calories_per_100g=167,
                        protein_per_100g=27,
                        fat_per_100g=8,
                        carbs_per_100g=0,
                    ),
                ],
                total_calories=490,
                overall_confidence=0.9,
                comment="t",
            )
        )
    )
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text(
        "убери курицу",
        context={"current_draft": draft},
    )
    assert len(out.items) == 1
    assert out.items[0].name == "гречка"


@pytest.mark.asyncio
async def test_add_apple_third_item() -> None:
    raw = _shell(
        mode="update",
        items=[
            _base_item(
                name="гречка",
                weight=200,
                portion="200 г",
                per_c=120,
                per_p=4,
                per_f=2,
                per_cb=24,
                cal=240,
                p=8,
                f=4,
                c=48,
            ),
            _base_item(
                name="курица",
                weight=150,
                portion="150 г",
                per_c=165,
                per_p=31,
                per_f=4,
                per_cb=0,
                cal=248,
                p=46,
                f=6,
                c=0,
            ),
            _base_item(
                name="яблоко",
                weight=100,
                portion="100 г",
                per_c=52,
                per_p=0.3,
                per_f=0.2,
                per_cb=14,
                cal=52,
                p=0.3,
                f=0.2,
                c=14,
            ),
        ],
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_openai_completion(_meal_json(raw)))
    settings = _stub_settings()
    cs = CalorieService()
    draft = cs.result_to_dict(
        cs.validate_food_result(
            FoodRecognitionResult(
                items=[
                    FoodItemRecognition(
                        name="гречка",
                        portion_description="200 г",
                        estimated_grams=200,
                        calories=240,
                        protein=8,
                        fat=4,
                        carbs=48,
                        calories_per_100g=120,
                        protein_per_100g=4,
                        fat_per_100g=2,
                        carbs_per_100g=24,
                    ),
                    FoodItemRecognition(
                        name="курица",
                        portion_description="150 г",
                        estimated_grams=150,
                        calories=250,
                        protein=40,
                        fat=8,
                        carbs=0,
                        calories_per_100g=167,
                        protein_per_100g=27,
                        fat_per_100g=8,
                        carbs_per_100g=0,
                    ),
                ],
                total_calories=490,
                overall_confidence=0.9,
                comment="t",
            )
        )
    )
    out = await FoodTextParserService(settings, openai_client=client).parse_food_text(
        "добавь яблоко 100 г",
        context={"current_draft": draft},
    )
    assert len(out.items) == 3
    assert any(i.name == "яблоко" for i in out.items)


@pytest.mark.asyncio
async def test_prior_user_message_in_envelope() -> None:
    raw = _shell(items=[_base_item(
        name="гречка",
        weight=200,
        portion="200 г",
        per_c=120,
        per_p=4,
        per_f=2,
        per_cb=24,
        cal=240,
        p=8,
        f=4,
        c=48,
    )])
    captured: dict[str, Any] = {}

    async def _cap(**kwargs: Any):
        captured.clear()
        captured.update(json.loads(kwargs["messages"][1]["content"]))
        return _mock_openai_completion(_meal_json(raw))

    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=_cap)
    settings = _stub_settings()
    await FoodTextParserService(settings, openai_client=client).parse_food_text(
        "200 г",
        context={"prior_user_message": "гречка"},
    )
    assert captured.get("prior_user_message") == "гречка"
