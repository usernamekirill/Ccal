from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.ai.speech_client import SpeechToTextService
from calorie_bot.app.ai.text_parser_service import FoodTextParserService
from calorie_bot.app.config import Settings
from calorie_bot.app.domain import MealSource
from calorie_bot.app.keyboards.meal import photo_review_keyboard
from calorie_bot.app.security.input_validation import ensure_audio_duration
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.services.correction_service import CorrectionService
from calorie_bot.app.services.goal_service import GoalService
from calorie_bot.app.services.onboarding_gate import food_logging_blocked_message
from calorie_bot.app.services.security_service import SecurityService
from calorie_bot.app.services.user_service import UserService
from calorie_bot.app.services.user_settings_service import create_user_settings_service
from calorie_bot.app.states.meal import MealStates
from calorie_bot.app.texts.settings import AI_DISABLED_HINT

router = Router(name="voice")


@router.message(F.voice | F.audio)
async def handle_voice_or_audio(
    message: Message,
    bot: Bot,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Handle Telegram voice messages and audio files as meal drafts or corrections."""
    if message.from_user is None:
        return

    telegram_audio = message.voice or message.audio
    if telegram_audio is None:
        return
    ensure_audio_duration(telegram_audio.duration, settings.max_audio_seconds)

    user = await UserService(session).ensure_user(message.from_user)
    blocked = food_logging_blocked_message(user)
    if blocked:
        await message.answer(blocked)
        return
    settings_svc = create_user_settings_service(session, GoalService())
    if not await settings_svc.is_ai_analysis_enabled(user.id):
        await message.answer(AI_DISABLED_HINT)
        return
    security = SecurityService(Path(settings.temp_media_dir))
    security.ensure_file_size(telegram_audio.file_size, settings.max_audio_bytes)

    audio_path: Path | None = None
    try:
        file = await bot.get_file(telegram_audio.file_id)
        audio_path = await security.download_temporary(bot, file, _audio_suffix(message))
        transcript = await SpeechToTextService(settings).transcribe(audio_path)
    finally:
        security.cleanup(audio_path)

    data = await state.get_data()
    calorie_service = CalorieService()
    if data.get("photo_food_result"):
        current = calorie_service.result_from_dict(data["photo_food_result"])
        updated = CorrectionService().apply_food_result_correction(current, transcript)
        await state.set_state(MealStates.photo_review)
        await state.update_data(
            photo_food_result=calorie_service.result_to_dict(updated),
            food_source=MealSource.MIXED.value,
            voice_transcript=transcript,
        )
        await message.answer(
            "Распознал голос и обновил текущий результат:\n\n"
            f"{calorie_service.format_result(updated)}",
            reply_markup=photo_review_keyboard(),
        )
        return

    result = await FoodTextParserService(settings).parse_food_text(transcript)

    await state.set_state(MealStates.photo_review)
    await state.update_data(
        photo_food_result=calorie_service.result_to_dict(result),
        food_source=MealSource.AUDIO.value,
        voice_transcript=transcript,
    )
    await message.answer(
        f"Распознал: {transcript}\n\n{calorie_service.format_result(result)}",
        reply_markup=photo_review_keyboard(),
    )


def _audio_suffix(message: Message) -> str:
    if message.voice:
        return ".ogg"
    if message.audio and message.audio.file_name and "." in message.audio.file_name:
        return "." + message.audio.file_name.rsplit(".", maxsplit=1)[1]
    return ".mp3"
