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
        from calorie_bot.app.nlp.meal_text_preprocess import (
            normalize_meal_input_text,
            try_parse_plaintext_meal_line,
        )
        from calorie_bot.app.services.calorie_service import CalorieService
        from calorie_bot.app.utils.openai_errors import translate_openai_exception

        nt = normalize_meal_input_text(text)
        quick = try_parse_plaintext_meal_line(nt)
        if quick is not None:
            return quick

        try:
            response = await self._client.chat.completions.create(
                model=self._settings.openai_correction_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": FOOD_TEXT_PARSER_PROMPT},
                    {"role": "user", "content": nt + default_hint},
                ],
            )
            content = response.choices[0].message.content or "{}"
            parsed = FoodRecognitionResult.model_validate_json(content)
            return CalorieService().validate_food_result(parsed)
        except Exception as exc:
            fb = try_parse_plaintext_meal_line(nt)
            if fb is not None:
                return fb
            raise translate_openai_exception(exc) from None
