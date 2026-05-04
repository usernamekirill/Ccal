from openai import AsyncOpenAI

from calorie_bot.app.ai.nlp.text_food_parser import TextFoodParser
from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.config import Settings
from calorie_bot.app.services.calorie_service import CalorieService


class FoodTextParserService:
    """Extract food items and calories from natural-language meal text."""

    def __init__(
        self,
        settings: Settings,
        *,
        openai_client: AsyncOpenAI | None = None,
    ) -> None:
        self._settings = settings
        self._client = openai_client

    async def parse_food_text(
        self,
        text: str,
        default_meal_type: str | None = None,
    ) -> FoodRecognitionResult:
        """Return a validated food recognition result from user text (OpenAI first, then offline fallbacks)."""
        from calorie_bot.app.nlp.meal_text_preprocess import (
            normalize_meal_input_text,
            try_parse_plaintext_meal_line,
        )

        calorie_service = CalorieService()
        nt = normalize_meal_input_text(text)
        draft = await TextFoodParser(self._settings, self._client).parse_food_text(
            nt,
            {"default_meal_type": default_meal_type},
        )

        if not draft.raw_parse_failed:
            fr = draft.food_result
            if fr.items or (fr.needs_clarification and (fr.clarification_question or "").strip()):
                return calorie_service.validate_food_result(fr)

        fb = try_parse_plaintext_meal_line(nt)
        if fb is not None:
            return calorie_service.validate_food_result(fb)

        return calorie_service.validate_food_result(
            FoodRecognitionResult(
                items=[],
                total_calories=0,
                overall_confidence=0.0,
                comment="Текст не распознан",
            ),
        )
