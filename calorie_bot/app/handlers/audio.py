from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.ai.nutrition_parser import NutritionParser
from calorie_bot.app.ai.speech_client import SpeechToTextService
from calorie_bot.app.ai.vision_client import VisionAIService
from calorie_bot.app.config import Settings
from calorie_bot.app.keyboards.meal import meal_confirmation_keyboard
from calorie_bot.app.messages.templates import meal_item_lines
from calorie_bot.app.messages.texts import render_meal_draft_text
from calorie_bot.app.repositories.ai_request_repository import AIRequestRepository
from calorie_bot.app.repositories.meal_repository import MealRepository
from calorie_bot.app.security.input_validation import ensure_audio_duration
from calorie_bot.app.services.correction_service import CorrectionService
from calorie_bot.app.services.meal_analysis_service import MealAnalysisService
from calorie_bot.app.services.meal_service import MealService, meal_model_to_draft
from calorie_bot.app.services.security_service import SecurityService
from calorie_bot.app.services.user_service import UserService

router = Router(name="audio")


@router.message(F.voice)
async def handle_voice(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Transcribe voice correction and apply it to the current meal draft."""
    if message.from_user is None or message.voice is None:
        return
    ensure_audio_duration(message.voice.duration, settings.max_audio_seconds)

    user = await UserService(session).ensure_user(message.from_user)
    security = SecurityService(Path(settings.temp_media_dir))
    security.ensure_file_size(message.voice.file_size, settings.max_audio_bytes)

    file = await bot.get_file(message.voice.file_id)
    audio_path: Path | None = None
    try:
        audio_path = await security.download_temporary(bot, file, ".ogg")
        analysis_service = MealAnalysisService(
            ai_request_repository=AIRequestRepository(session),
            vision_service=VisionAIService(settings),
            speech_service=SpeechToTextService(settings),
            correction_service=CorrectionService(),
            parser=NutritionParser(),
            settings=settings,
        )
        transcript = await analysis_service.transcribe_audio(user.id, audio_path)
    finally:
        security.cleanup(audio_path)

    meal_service = MealService(MealRepository(session))
    latest = await meal_service.latest_draft(user.id)
    draft = analysis_service.apply_text_correction(
        meal_model_to_draft(latest) if latest else None,
        transcript,
    )
    if latest:
        await meal_service.apply_draft_update(latest, draft)
    else:
        await message.answer("Не нашел черновик. Напиши еду текстом или отправь фото.")
        return

    await message.answer(
        render_meal_draft_text(
            items=meal_item_lines(draft),
            total_calories=draft.total_calories,
            confidence=draft.confidence,
            notes=f"Распознал голос: {transcript}",
        ),
        reply_markup=meal_confirmation_keyboard(),
    )
