import base64
from pathlib import Path

from openai import AsyncOpenAI

from calorie_bot.app.ai.prompts import PHOTO_RECOGNITION_SYSTEM_PROMPT
from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.config import Settings


class AIPhotoService:
    """Recognize food from compressed meal photos using an AI vision model."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
        )

    async def recognize_food(self, image_path: Path) -> FoodRecognitionResult:
        """Return a validated food recognition result for a local image file."""
        encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")
        try:
            response = await self._client.chat.completions.create(
                model=self._settings.openai_vision_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": PHOTO_RECOGNITION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Верни только JSON по схеме."},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"},
                            },
                        ],
                    },
                ],
            )
        except Exception as exc:
            from calorie_bot.app.utils.openai_errors import translate_openai_exception

            raise translate_openai_exception(exc) from None
        content = response.choices[0].message.content or "{}"
        return FoodRecognitionResult.model_validate_json(content)
