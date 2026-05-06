from openai import AsyncOpenAI

from calorie_bot.app.ai.nlp.text_food_parser import TextFoodParser
from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.config import Settings
from calorie_bot.app.services.calorie_service import CalorieService


class FoodTextParserService:
    """Extract food items and calories from natural-language meal text (OpenAI-first)."""

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
        *,
        context: dict | None = None,
    ) -> FoodRecognitionResult:
        """Return a validated food recognition result (always via OpenAI; no local meal parsing)."""
        calorie_service = CalorieService()
        ctx: dict = dict(context) if context else {}
        if default_meal_type is not None:
            ctx.setdefault("default_meal_type", default_meal_type)
        cd = ctx.get("current_draft")
        if isinstance(cd, dict):
            ctx["current_draft"] = calorie_service.result_from_dict(cd)

        draft = await TextFoodParser(self._settings, self._client).parse_food_text(text, ctx)

        def _soft_failure() -> FoodRecognitionResult:
            return calorie_service.validate_food_result(
                FoodRecognitionResult(
                    items=[],
                    total_calories=0,
                    overall_confidence=0.35,
                    comment="Нужно уточнение",
                    needs_clarification=True,
                    clarification_question=(
                        "Не вышло обработать ответ модели. Напишите ещё раз, что вы съели "
                        "(можно своими словами; вес укажите, если знаете)."
                    ),
                )
            )

        if draft.raw_parse_failed:
            return _soft_failure()

        out = calorie_service.validate_food_result(draft.food_result)
        has_clar = bool(out.needs_clarification and (out.clarification_question or "").strip())
        if out.items or has_clar:
            return out
        return _soft_failure()
