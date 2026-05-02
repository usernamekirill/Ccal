"""Apply natural-language edits to a FoodRecognitionResult via the LLM."""

from openai import AsyncOpenAI

from calorie_bot.app.ai.prompts import FOOD_CORRECTION_PROMPT
from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.config import Settings


class FoodResultCorrectionService:
    """Merge user free-text instructions into the current recognition JSON."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
        )

    async def apply(self, current: FoodRecognitionResult, instruction: str) -> FoodRecognitionResult:
        """Return an updated result; instruction may add/remove items or change grams/calories."""
        payload = (
            f"Текущий JSON:\n{current.model_dump_json()}\n\n"
            f"Правка пользователя:\n{instruction.strip()}"
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._settings.openai_correction_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": FOOD_CORRECTION_PROMPT},
                    {"role": "user", "content": payload},
                ],
            )
        except Exception as exc:
            from calorie_bot.app.utils.openai_errors import translate_openai_exception

            raise translate_openai_exception(exc) from None
        content = response.choices[0].message.content or "{}"
        from calorie_bot.app.services.calorie_service import CalorieService

        parsed = FoodRecognitionResult.model_validate_json(content)
        return CalorieService().validate_food_result(parsed)
