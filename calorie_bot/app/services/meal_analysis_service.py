from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from calorie_bot.app.ai.nutrition_parser import NutritionParser
from calorie_bot.app.ai.speech_client import SpeechToTextService
from calorie_bot.app.ai.vision_client import VisionAIService
from calorie_bot.app.config import Settings
from calorie_bot.app.domain import AIRequestStatus, AIRequestType, MealDraft, MealSource
from calorie_bot.app.repositories.ai_request_repository import AIRequestRepository
from calorie_bot.app.services.correction_service import CorrectionService


class MealAnalysisService:
    """Coordinate AI meal analysis, speech-to-text, and compact corrections."""

    def __init__(
        self,
        ai_request_repository: AIRequestRepository,
        vision_service: VisionAIService,
        speech_service: SpeechToTextService,
        correction_service: CorrectionService,
        parser: NutritionParser,
        settings: Settings,
    ) -> None:
        self._ai_request_repository = ai_request_repository
        self._vision_service = vision_service
        self._speech_service = speech_service
        self._correction_service = correction_service
        self._parser = parser
        self._settings = settings

    async def analyze_photo(self, user_id: int, image_path: Path) -> MealDraft:
        """Analyze a meal photo and return a draft requiring confirmation."""
        await self._ensure_soft_limit(user_id)
        request = await self._ai_request_repository.create(
            user_id=user_id,
            request_type=AIRequestType.VISION.value,
            status=AIRequestStatus.STARTED.value,
            model=self._settings.openai_vision_model,
        )
        try:
            analysis = await self._vision_service.analyze_meal_photo(image_path)
        except Exception as exc:
            await self._ai_request_repository.mark_failed(request, type(exc).__name__)
            raise
        await self._ai_request_repository.mark_succeeded(request)
        return self._parser.to_meal_draft(analysis, MealSource.PHOTO)

    async def transcribe_audio(self, user_id: int, audio_path: Path) -> str:
        """Transcribe a voice message without storing sensitive audio."""
        await self._ensure_soft_limit(user_id)
        request = await self._ai_request_repository.create(
            user_id=user_id,
            request_type=AIRequestType.SPEECH_TO_TEXT.value,
            status=AIRequestStatus.STARTED.value,
            model=self._settings.openai_speech_model,
        )
        try:
            text = await self._speech_service.transcribe(audio_path)
        except Exception as exc:
            await self._ai_request_repository.mark_failed(request, type(exc).__name__)
            raise
        await self._ai_request_repository.mark_succeeded(request)
        return text

    def apply_text_correction(self, current: MealDraft | None, text: str) -> MealDraft:
        """Apply a text correction locally before escalating to AI in later versions."""
        return self._correction_service.apply_text(current, text)

    async def _ensure_soft_limit(self, user_id: int) -> None:
        timezone = ZoneInfo(self._settings.timezone)
        today = datetime.now(timezone).replace(hour=0, minute=0, second=0, microsecond=0)
        count = await self._ai_request_repository.count_for_user_since(user_id, today)
        if count >= self._settings.ai_daily_soft_limit:
            raise RuntimeError("ai_daily_soft_limit_reached")
