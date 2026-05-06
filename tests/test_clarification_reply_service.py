"""ClarificationReplyService: deterministic fallback path without OpenAI."""

import pytest
from pydantic import SecretStr

from calorie_bot.app.ai.clarification_orchestrator import build_llm_context
from calorie_bot.app.ai.clarification_reply_service import ClarificationReplyService
from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.config import Settings
from calorie_bot.app.services.calorie_service import CalorieService


def _settings_offline() -> Settings:
    return Settings(
        telegram_bot_token=SecretStr("x"),
        openai_api_key=SecretStr(""),
        database_url="sqlite+aiosqlite:///:memory:",
    )


@pytest.mark.asyncio
async def test_build_reply_uses_fallback_when_openai_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    """CASE 2 path: service still returns one short message + keyboard on LLM failure."""
    svc = CalorieService()
    it = FoodItemRecognition.model_validate(
        {
            "name": "творог",
            "portion_description": "порция",
            "estimated_grams": None,
            "calories": 0,
        }
    )
    r = FoodRecognitionResult(
        items=[it],
        total_calories=0,
        overall_confidence=0.85,
        comment="x",
        needs_clarification=True,
    )
    r = svc.validate_food_result(r)
    r = svc.apply_clarification_guards(r)
    ctx = build_llm_context(r, svc)

    async def boom(self, ctx_inner):
        raise RuntimeError("no_api")

    monkeypatch.setattr(ClarificationReplyService, "generate_card", boom)
    service = ClarificationReplyService(_settings_offline())
    text, kb, merged = await service.build_reply_for_result(r, ctx)
    assert "творог" in text.lower()
    assert kb is not None
    assert merged.clarification_question
    assert "пармезан" not in text.lower()
