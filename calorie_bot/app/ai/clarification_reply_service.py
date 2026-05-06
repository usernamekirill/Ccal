"""One-shot OpenAI clarification card: single conversational message + optional gram presets."""

from __future__ import annotations

import json
import logging
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from calorie_bot.app.ai.clarification_orchestrator import (
    ClarificationLLMContext,
    fallback_clarification_body,
    portion_presets_for_dish,
)
from calorie_bot.app.ai.prompts import CLARIFICATION_ASSISTANT_SYSTEM_PROMPT
from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.config import Settings
from calorie_bot.app.keyboards.meal import contextual_portion_keyboard

_log = logging.getLogger(__name__)


class QuickActionSpec(BaseModel):
    """One inline preset the user can tap (grams sent as synthetic text follow-up)."""

    grams: int = Field(ge=10, le=9000)
    label: str = Field(min_length=1, max_length=48)


class ClarificationReplyPayload(BaseModel):
    """Strict JSON from the clarification model."""

    primary_issue: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=1600)
    quick_actions: list[QuickActionSpec] = Field(default_factory=list, max_length=5)
    expects_input_type: Literal["grams", "portion_text", "free_text"] = "grams"


class ClarificationReplyService:
    """Generate a single premium clarification turn (Telegram-native, context-aware)."""

    def __init__(self, settings: Settings, *, openai_client: AsyncOpenAI | None = None) -> None:
        self._settings = settings
        self._client = openai_client or AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
        )

    async def generate_card(
        self,
        ctx: ClarificationLLMContext,
    ) -> tuple[str, ClarificationReplyPayload]:
        """Return Telegram text + parsed payload (for keyboard assembly)."""
        user_obj = {
            "dish_line": ctx.dish_line,
            "dish_emoji": ctx.dish_emoji,
            "recognized_items": ctx.recognized_items,
            "primary_issue": ctx.primary_issue,
            "missing_fields": ctx.missing_fields,
            "prior_model_question": ctx.prior_model_question,
            "overall_confidence": ctx.overall_confidence,
            "allowed_actions": ["suggest_gram_presets", "ask_free_text_reply"],
        }
        try:
            response = await self._client.chat.completions.create(
                model=self._settings.openai_correction_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": CLARIFICATION_ASSISTANT_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(user_obj, ensure_ascii=False)},
                ],
            )
        except Exception:
            _log.exception("clarification_openai_call_failed")
            raise
        raw = response.choices[0].message.content or "{}"
        payload = ClarificationReplyPayload.model_validate_json(raw)
        text = (payload.message or "").strip()
        if not text:
            raise ValueError("empty_clarification_message")
        return (text, payload)

    async def build_reply_for_result(
        self,
        result: FoodRecognitionResult,
        ctx: ClarificationLLMContext,
    ) -> tuple[str, object | None, FoodRecognitionResult]:
        """Produce UI line + keyboard + result with a single stored clarification_question."""
        try:
            message, payload = await self.generate_card(ctx)
            actions = [(a.grams, a.label) for a in payload.quick_actions]
            if ctx.primary_issue == "missing_weight" and len(actions) < 2:
                actions = portion_presets_for_dish(ctx.dish_line)
            kb = contextual_portion_keyboard(actions) if ctx.primary_issue == "missing_weight" else None
            merged = result.model_copy(
                update={
                    "clarification_question": message,
                    "needs_clarification": True,
                }
            )
            return (message, kb, merged)
        except Exception:
            _log.warning("clarification_ai_fallback", extra={"issue": ctx.primary_issue})
            body = fallback_clarification_body(ctx)
            actions = (
                portion_presets_for_dish(ctx.dish_line)
                if ctx.primary_issue == "missing_weight"
                else []
            )
            kb = contextual_portion_keyboard(actions) if actions else None
            merged = result.model_copy(
                update={
                    "clarification_question": body,
                    "needs_clarification": True,
                }
            )
            return (body, kb, merged)
