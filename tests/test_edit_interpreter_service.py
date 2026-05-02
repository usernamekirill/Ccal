"""Tests for LLM+gram-priority merge in edit_interpreter_service."""

import pytest
from pydantic import SecretStr

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.config import Settings
from calorie_bot.app.services.edit_interpreter_service import apply_instruction_to_food_result


def _one_item(*, grams: float, calories: int) -> FoodRecognitionResult:
    return FoodRecognitionResult(
        items=[
            FoodItemRecognition(
                name="кулич",
                portion_description=f"{grams:.0f} г",
                estimated_grams=grams,
                calories=calories,
                protein=None,
                fat=None,
                carbs=None,
                confidence=0.9,
            )
        ],
        total_calories=calories,
        overall_confidence=0.9,
        comment="t",
    )


@pytest.mark.asyncio
async def test_user_grams_override_after_llm_returns_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """If LLM echoes AI portion, explicit grams in instruction still rescale kcal."""
    class FakeCorr:
        def __init__(self, _settings: Settings) -> None:
            pass

        async def apply(
            self,
            current: FoodRecognitionResult,
            instruction: str,
        ) -> FoodRecognitionResult:
            return current.model_copy(deep=True)

    monkeypatch.setattr(
        "calorie_bot.app.services.edit_interpreter_service.FoodResultCorrectionService",
        FakeCorr,
    )
    settings = Settings.model_construct(
        openai_api_key=SecretStr("sk-test"),
        telegram_bot_token=SecretStr("1:test"),
    )
    current = _one_item(grams=150, calories=450)
    out = await apply_instruction_to_food_result(settings, "сделай 50 грамм", current)
    assert out.items[0].estimated_grams == 50
    assert out.items[0].calories == 150
    assert out.total_calories == 150
