"""Apply free-text or transcribed instructions to a food recognition draft (LLM + gram priority)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from calorie_bot.app.ai.food_result_correction_service import FoodResultCorrectionService
from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.config import Settings
from calorie_bot.app.domain import GramsSource
from calorie_bot.app.services.calorie_service import CalorieService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def apply_instruction_to_food_result(
    settings: Settings,
    instruction: str,
    current: FoodRecognitionResult,
    *,
    grams_source: GramsSource = GramsSource.TEXT_CORRECTION,
    session: AsyncSession | None = None,
) -> FoodRecognitionResult:
    """Update recognition JSON from a user phrase; explicit grams in the phrase still win."""
    svc = CalorieService()
    llm_patch = await FoodResultCorrectionService(settings).apply(current, instruction.strip())
    merged = svc.apply_user_text_gram_priority(
        instruction,
        llm_patch,
        grams_source=grams_source.value,
    )
    merged = svc.validate_food_result(merged)
    if session is not None:
        merged = await svc.enrich_after_text_processing(merged, instruction, session, settings)
    return svc.validate_food_result(merged)
