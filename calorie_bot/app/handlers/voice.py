import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.ai.speech_client import SpeechToTextService
from calorie_bot.app.ai.text_parser_service import FoodTextParserService
from calorie_bot.app.config import Settings
from calorie_bot.app.domain import GramsSource, MealSource
from calorie_bot.app.keyboards.confirmation import recognition_trouble_keyboard
from calorie_bot.app.keyboards.meal import photo_review_keyboard
from calorie_bot.app.messages.texts import (
    RECOGNITION_UNCERTAIN_TEXT,
    TEXT_FOOD_CLARIFICATION_PREFIX,
)
from calorie_bot.app.security.input_validation import ensure_audio_duration
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.services.edit_interpreter_service import apply_instruction_to_food_result
from calorie_bot.app.services.goal_service import GoalService
from calorie_bot.app.services.onboarding_gate import food_logging_blocked_message
from calorie_bot.app.services.security_service import SecurityService
from calorie_bot.app.services.user_service import UserService
from calorie_bot.app.services.user_settings_service import create_user_settings_service
from calorie_bot.app.states.meal import MealStates
from calorie_bot.app.texts.settings import AI_DISABLED_HINT
from calorie_bot.app.utils.clarification_state import fsm_data_blocking_text_clarification
from calorie_bot.app.utils.meal_type import infer_meal_type

router = Router(name="voice")
_log = logging.getLogger(__name__)


@router.message(F.voice | F.audio)
async def handle_voice_or_audio(
    message: Message,
    bot: Bot,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Handle voice/audio: refine an open draft or parse a new meal from transcript."""
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
    st = await state.get_state()

    if data.get("photo_food_result") and st in (
        MealStates.photo_review.state,
        MealStates.photo_editing.state,
    ):
        current = calorie_service.result_from_dict(data["photo_food_result"])
        try:
            updated = await apply_instruction_to_food_result(
                settings,
                transcript,
                current,
                grams_source=GramsSource.VOICE_CORRECTION,
                session=session,
            )
        except Exception:
            await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
            return
        updated = calorie_service.apply_clarification_guards(updated)
        if calorie_service.requires_blocking_clarification(updated):
            await state.set_state(MealStates.waiting_for_correction)
            await state.update_data(
                photo_food_result=calorie_service.result_to_dict(updated),
                clarification_mode="photo",
                voice_transcript=transcript,
            )
            await message.answer(f"{TEXT_FOOD_CLARIFICATION_PREFIX}\n{updated.clarification_question}")
            return
        await state.set_state(MealStates.photo_review)
        await state.update_data(
            photo_food_result=calorie_service.result_to_dict(updated),
            food_source=MealSource.MIXED.value,
            voice_transcript=transcript,
            photo_edit_action=None,
        )
        body = calorie_service.format_result(updated)
        if updated.needs_clarification and updated.clarification_question:
            body = f"{body}\n\n⚠️ {updated.clarification_question}"
        await message.answer(
            f"Учёл: «{transcript}»\n\n{body}",
            reply_markup=photo_review_keyboard(),
        )
        return

    timezone = ZoneInfo(settings.timezone)
    default_meal_type = infer_meal_type(datetime.now(timezone))
    try:
        result = await FoodTextParserService(settings).parse_food_text(
            transcript,
            default_meal_type=default_meal_type.value,
        )
    except Exception:
        _log.exception("voice_meal_parse_failed")
        await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
        return

    result = calorie_service.with_default_meal_type(result, default_meal_type)
    result = calorie_service.apply_user_text_gram_priority(transcript, result)
    try:
        result = await calorie_service.enrich_after_text_processing(
            result, transcript, session, settings
        )
    except Exception:
        _log.exception("voice_meal_enrich_failed")
        await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
        return

    result = calorie_service.apply_clarification_guards(result)
    if calorie_service.requires_blocking_clarification(result):
        await state.set_state(MealStates.waiting_for_correction)
        await state.update_data(
            **fsm_data_blocking_text_clarification(
                calorie_service,
                result,
                pending_text=transcript,
                default_meal_type=default_meal_type.value,
                voice_transcript=transcript,
            ),
        )
        await message.answer(f"{TEXT_FOOD_CLARIFICATION_PREFIX}\n{result.clarification_question}")
        return

    if not result.items:
        if result.needs_clarification and result.clarification_question:
            await state.set_state(MealStates.waiting_for_correction)
            await state.update_data(
                pending_text_food=transcript,
                default_meal_type=default_meal_type.value,
                clarification_mode=None,
                pending_food_result_draft=None,
            )
            await message.answer(f"{TEXT_FOOD_CLARIFICATION_PREFIX} {result.clarification_question}")
        else:
            await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
        return

    await state.set_state(MealStates.photo_review)
    await state.update_data(
        photo_food_result=calorie_service.result_to_dict(result),
        food_source=MealSource.AUDIO.value,
        voice_transcript=transcript,
        clarification_mode=None,
        pending_food_result_draft=None,
        pending_text_food=None,
    )
    body = calorie_service.format_result(result)
    if result.needs_clarification and result.clarification_question:
        body = f"{body}\n\n⚠️ {result.clarification_question}"
    await message.answer(
        f"Распознал: {transcript}\n\n{body}",
        reply_markup=photo_review_keyboard(),
    )


def _audio_suffix(message: Message) -> str:
    if message.voice:
        return ".ogg"
    if message.audio and message.audio.file_name and "." in message.audio.file_name:
        return "." + message.audio.file_name.rsplit(".", maxsplit=1)[1]
    return ".mp3"
