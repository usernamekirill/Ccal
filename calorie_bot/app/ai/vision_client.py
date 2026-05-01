import base64
from pathlib import Path

from openai import AsyncOpenAI

from calorie_bot.app.ai.prompts import VISION_MEAL_PROMPT
from calorie_bot.app.ai.schemas import MealAnalysis
from calorie_bot.app.config import Settings


class VisionAIService:
    """Analyze meal photos through an external vision model."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
        )

    async def analyze_meal_photo(self, image_path: Path) -> MealAnalysis:
        """Return a structured meal analysis for a local image file."""
        image_data = base64.b64encode(image_path.read_bytes()).decode("ascii")
        try:
            response = await self._client.chat.completions.create(
                model=self._settings.openai_vision_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": VISION_MEAL_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Return only compact JSON for this meal."},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                            },
                        ],
                    },
                ],
            )
        except Exception as exc:
            from calorie_bot.app.utils.openai_errors import translate_openai_exception

            raise translate_openai_exception(exc) from None
        content = response.choices[0].message.content or "{}"
        return MealAnalysis.model_validate_json(content)
