"""Structured text meal NLP (LLM + normalization helpers)."""

from __future__ import annotations

from openai import AsyncOpenAI

from calorie_bot.app.ai.nlp.text_food_parser import ParsedMealDraft, TextFoodParser, structured_meal_to_food_result
from calorie_bot.app.config import Settings

__all__ = [
    "ParsedMealDraft",
    "TextFoodParser",
    "parse_food_text",
    "structured_meal_to_food_result",
]


async def parse_food_text(
    user_text: str,
    *,
    settings: Settings,
    context: dict | None = None,
    client: AsyncOpenAI | None = None,
) -> ParsedMealDraft:
    """Call the structured OpenAI text-food parser (no database)."""
    return await TextFoodParser(settings, client).parse_food_text(user_text, context)
