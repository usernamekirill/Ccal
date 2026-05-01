from openai import AsyncOpenAI

from calorie_bot.app.ai.prompts import FOOD_TEXT_PARSER_PROMPT
from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.config import Settings


class FoodTextParserService:
    """Extract food items and calories from natural-language meal text."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
        )

    async def parse_food_text(
        self,
        text: str,
        default_meal_type: str | None = None,
    ) -> FoodRecognitionResult:
        """Return a validated food recognition result from user text."""
        default_hint = (
            f"\nЕсли тип приема пищи не указан, используй meal_type={default_meal_type}."
            if default_meal_type
            else ""
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._settings.openai_correction_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": FOOD_TEXT_PARSER_PROMPT},
                    {"role": "user", "content": text + default_hint},
                ],
            )
        except Exception as exc:
            from calorie_bot.app.utils.openai_errors import translate_openai_exception

            raise translate_openai_exception(exc) from None
        content = response.choices[0].message.content or "{}"
        return FoodRecognitionResult.model_validate_json(content)
