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
from calorie_bot.app.domain import MealSource
from calorie_bot.app.keyboards.confirmation import recognition_trouble_keyboard
from calorie_bot.app.keyboards.meal import photo_review_keyboard
from calorie_bot.app.messages.texts import (
    RECOGNITION_UNCERTAIN_TEXT,
    TEXT_FOOD_PROCESSING_TEXT,
)
from calorie_bot.app.security.input_validation import ensure_audio_duration, ensure_meal_text_length
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.services.goal_service import GoalService
from calorie_bot.app.services.onboarding_gate import food_logging_blocked_message
from calorie_bot.app.services.security_service import SecurityService
from calorie_bot.app.services.user_service import UserService
from calorie_bot.app.services.user_settings_service import create_user_settings_service
from calorie_bot.app.states.meal import MealStates
from calorie_bot.app.texts.settings import AI_DISABLED_HINT
from calorie_bot.app.utils.clarification_state import fsm_data_blocking_text_clarification
from calorie_bot.app.utils.clarification_ux import (
    build_blocking_clarification_ui,
    format_clarification_followup_prompt,
)
from calorie_bot.app.utils.draft_parse_context import (
    meal_parse_context,
    unresolved_clarifications_from_recognition,
)
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

    timezone = ZoneInfo(settings.timezone)
    data = await state.get_data()
    calorie_service = CalorieService()
    st = await state.get_state()

    if st == MealStates.waiting_for_weight.state and data.get("pending_food_result_draft"):
        ensure_meal_text_length(transcript.strip(), settings.max_meal_text_chars)
        _dmt = data.get("default_meal_type")
        default_meal_type = (
            str(_dmt).strip()
            if _dmt is not None and str(_dmt).strip()
            else infer_meal_type(datetime.now(timezone)).value
        )
        await message.answer(TEXT_FOOD_PROCESSING_TEXT)
        pending_fr = calorie_service.result_from_dict(data["pending_food_result_draft"])
        unresolved = unresolved_clarifications_from_recognition(pending_fr)
        try:
            result = await FoodTextParserService(settings).parse_food_text(
                transcript.strip(),
                default_meal_type=default_meal_type,
                context=meal_parse_context(
                    data,
                    current_draft=data["pending_food_result_draft"],
                    unresolved_clarifications=unresolved,
                ),
            )
        except Exception:
            _log.exception("voice_weight_followup_parse_failed")
            await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
            return
        result = calorie_service.with_default_meal_type(result, infer_meal_type(datetime.now(timezone)))
        try:
            result = await calorie_service.enrich_after_text_processing(
                result, transcript, session, settings
            )
        except Exception:
            _log.exception("voice_weight_followup_enrich_failed")
            await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
            return
        result = calorie_service.apply_clarification_guards(result)
        if calorie_service.requires_blocking_clarification(result):
            _cl, _kb, result = await build_blocking_clarification_ui(
                calorie_service=calorie_service, result=result, settings=settings
            )
            next_state = (
                MealStates.waiting_for_weight
                if calorie_service.is_portion_weight_blocking_only(result)
                else MealStates.waiting_for_correction
            )
            await state.set_state(next_state)
            await state.update_data(
                **fsm_data_blocking_text_clarification(
                    calorie_service,
                    result,
                    pending_text=str(data.get("pending_text_food") or transcript),
                    default_meal_type=default_meal_type,
                    voice_transcript=transcript,
                ),
            )
            await message.answer(_cl, reply_markup=_kb)
            return
        if not result.items:
            if result.needs_clarification and result.clarification_question:
                await state.set_state(MealStates.waiting_for_correction)
                await state.update_data(
                    pending_text_food=str(data.get("pending_text_food") or ""),
                    default_meal_type=default_meal_type,
                    clarification_mode=None,
                    pending_food_result_draft=None,
                    pending_food=None,
                    voice_transcript=transcript,
                )
                await message.answer(format_clarification_followup_prompt(result))
            else:
                await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
            return
        await state.set_state(MealStates.photo_review)
        await state.update_data(
            photo_food_result=calorie_service.result_to_dict(result),
            food_source=MealSource.AUDIO.value,
            pending_text_food=None,
            pending_food_result_draft=None,
            pending_food=None,
            clarification_mode=None,
            voice_transcript=transcript,
        )
        body = calorie_service.format_result(result)
        await message.answer(
            f"Учёл: «{transcript}»\n\n{body}",
            reply_markup=photo_review_keyboard(),
        )
        return

    if data.get("photo_food_result") and st in (
        MealStates.photo_review.state,
        MealStates.photo_editing.state,
    ):
        current = calorie_service.result_from_dict(data["photo_food_result"])
        ensure_meal_text_length(transcript.strip(), settings.max_meal_text_chars)
        default_mt = current.meal_type or infer_meal_type(datetime.now(timezone)).value
        await message.answer(TEXT_FOOD_PROCESSING_TEXT)
        unresolved = unresolved_clarifications_from_recognition(current)
        try:
            updated = await FoodTextParserService(settings).parse_food_text(
                transcript.strip(),
                default_meal_type=default_mt,
                context=meal_parse_context(
                    data,
                    current_draft=current,
                    unresolved_clarifications=unresolved,
                ),
            )
        except Exception:
            _log.exception("voice_draft_edit_parse_failed")
            await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
            return
        updated = calorie_service.with_default_meal_type(updated, infer_meal_type(datetime.now(timezone)))
        try:
            updated = await calorie_service.enrich_after_text_processing(
                updated, transcript, session, settings
            )
        except Exception:
            _log.exception("voice_draft_edit_enrich_failed")
            await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
            return
        updated = calorie_service.apply_clarification_guards(updated)
        if calorie_service.requires_blocking_clarification(updated):
            _c, _kb, updated = await build_blocking_clarification_ui(
                calorie_service=calorie_service,
                result=updated,
                settings=settings,
            )
            await state.set_state(MealStates.waiting_for_correction)
            await state.update_data(
                photo_food_result=calorie_service.result_to_dict(updated),
                clarification_mode="photo",
                voice_transcript=transcript,
            )
            await message.answer(_c, reply_markup=_kb)
            return
        await state.set_state(MealStates.photo_review)
        await state.update_data(
            photo_food_result=calorie_service.result_to_dict(updated),
            food_source=MealSource.MIXED.value,
            voice_transcript=transcript,
            photo_edit_action=None,
        )
        body = calorie_service.format_result(updated)
        await message.answer(
            f"Учёл: «{transcript}»\n\n{body}",
            reply_markup=photo_review_keyboard(),
        )
        return

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
        _cl, _kb, result = await build_blocking_clarification_ui(
            calorie_service=calorie_service, result=result, settings=settings
        )
        next_state = (
            MealStates.waiting_for_weight
            if calorie_service.is_portion_weight_blocking_only(result)
            else MealStates.waiting_for_correction
        )
        await state.set_state(next_state)
        await state.update_data(
            **fsm_data_blocking_text_clarification(
                calorie_service,
                result,
                pending_text=transcript,
                default_meal_type=default_meal_type.value,
                voice_transcript=transcript,
            ),
        )
        await message.answer(_cl, reply_markup=_kb)
        return

    if not result.items:
        if result.needs_clarification and result.clarification_question:
            await state.set_state(MealStates.waiting_for_correction)
            await state.update_data(
                pending_text_food=transcript,
                default_meal_type=default_meal_type.value,
                clarification_mode=None,
                pending_food_result_draft=None,
                pending_food=None,
            )
            await message.answer(format_clarification_followup_prompt(result))
        else:
            await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
        return

    await state.set_state(MealStates.photo_review)
    await state.update_data(
        photo_food_result=calorie_service.result_to_dict(result),
        food_source=MealSource.AUDIO.value,
        vision_baseline_snapshot=None,
        voice_transcript=transcript,
        clarification_mode=None,
        pending_food_result_draft=None,
        pending_text_food=None,
        pending_food=None,
    )
    body = calorie_service.format_result(result)
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
