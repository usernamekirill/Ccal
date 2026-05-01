from openai import AsyncOpenAI

from calorie_bot.app.ai.prompts import NUTRITION_ESTIMATE_PROMPT
from calorie_bot.app.ai.schemas import FoodNutritionEstimateSchema
from calorie_bot.app.config import Settings
from calorie_bot.app.services.calorie_service import NutritionEstimate


class AINutritionEstimatorService:
    """Estimate nutrition values for a food when cache has no match."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
        )

    async def estimate_food(self, food_name: str) -> NutritionEstimate:
        """Return nutrition estimate for a food per 100 grams."""
        try:
            response = await self._client.chat.completions.create(
                model=self._settings.openai_correction_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": NUTRITION_ESTIMATE_PROMPT},
                    {"role": "user", "content": food_name},
                ],
            )
        except Exception as exc:
            from calorie_bot.app.utils.openai_errors import translate_openai_exception

            raise translate_openai_exception(exc) from None
        content = response.choices[0].message.content or "{}"
        parsed = FoodNutritionEstimateSchema.model_validate_json(content)
        return NutritionEstimate(
            display_name=parsed.display_name,
            calories_per_100g=parsed.calories_per_100g,
            protein_per_100g=parsed.protein_per_100g,
            fat_per_100g=parsed.fat_per_100g,
            carbs_per_100g=parsed.carbs_per_100g,
            confidence=parsed.confidence,
            is_estimated=True,
        )
