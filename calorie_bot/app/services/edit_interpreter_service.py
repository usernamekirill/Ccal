"""Apply free-text or transcribed instructions to a food recognition draft (LLM + gram priority)."""

from calorie_bot.app.ai.food_result_correction_service import FoodResultCorrectionService
from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.config import Settings
from calorie_bot.app.services.calorie_service import CalorieService


async def apply_instruction_to_food_result(
    settings: Settings,
    instruction: str,
    current: FoodRecognitionResult,
) -> FoodRecognitionResult:
    """Update recognition JSON from a user phrase; explicit grams in the phrase still win."""
    svc = CalorieService()
    llm_patch = await FoodResultCorrectionService(settings).apply(current, instruction.strip())
    merged = svc.apply_user_text_gram_priority(instruction, llm_patch)
    return svc.validate_food_result(merged)
