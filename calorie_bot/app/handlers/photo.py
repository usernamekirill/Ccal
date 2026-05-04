import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.ai.photo_service import AIPhotoService
from calorie_bot.app.config import Settings
from calorie_bot.app.database.telegram_safe_commit import commit_db_work_before_telegram
from calorie_bot.app.domain import MealSource, MealStatus, MealType
from calorie_bot.app.keyboards.confirmation import draft_cancelled_keyboard, recognition_trouble_keyboard
from calorie_bot.app.keyboards.meal import photo_review_keyboard
from calorie_bot.app.keyboards.nav_footer import navigation_footer_keyboard
from calorie_bot.app.messages.texts import (
    MEAL_NOT_FOUND_TEXT,
    PHOTO_EDIT_ERROR_TEXT,
    PHOTO_EDIT_FLEX_TEXT,
    PHOTO_PROCESSING_TEXT,
    PHOTO_QUICK_ADD_TEXT,
    PHOTO_QUICK_DELETE_TEXT,
    RECOGNITION_UNCERTAIN_TEXT,
    TEXT_FOOD_CLARIFICATION_PREFIX,
)
from calorie_bot.app.messages.ux_flow import MEAL_CANCEL_FOLLOWUP
from calorie_bot.app.post_action_message import send_post_action_message
from calorie_bot.app.repositories.meal_change_log_repository import MealChangeLogRepository
from calorie_bot.app.repositories.meal_repository import MealRepository
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.services.edit_interpreter_service import apply_instruction_to_food_result
from calorie_bot.app.services.daily_stats_sync import on_confirmed_meal_edited, on_meal_confirmed
from calorie_bot.app.services.goal_service import GoalService
from calorie_bot.app.services.meal_service import MealService
from calorie_bot.app.services.motivation_service import create_motivation_service
from calorie_bot.app.services.onboarding_gate import food_logging_blocked_message
from calorie_bot.app.services.security_service import SecurityService
from calorie_bot.app.services.user_service import UserService
from calorie_bot.app.services.user_settings_service import create_user_settings_service
from calorie_bot.app.states.meal import MealStates
from calorie_bot.app.texts.settings import AI_DISABLED_HINT
from calorie_bot.app.utils.image_processor import ImageProcessor
from calorie_bot.app.utils.meal_type import infer_meal_type

router = Router(name="photo")

_log = logging.getLogger(__name__)

_STALE_DRAFT_HINT = (
    "Черновик недоступен (сессия сброшена или сообщение устарело). "
    "Отправьте еду снова — фото, голос или текст."
)


async def _reject_if_no_photo_draft(callback: CallbackQuery, state: FSMContext) -> bool:
    """If FSM lost track of the open draft, tell the user and stop (avoids silent inline buttons)."""
    data = await state.get_data()
    if data.get("photo_food_result"):
        return False
    await callback.answer(_STALE_DRAFT_HINT, show_alert=True)
    return True


async def _edit_or_answer_followup(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup,
) -> None:
    """Prefer editing the card in place; fall back to a new message if Telegram rejects edit."""
    if callback.message is None:
        return
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=reply_markup)


@router.message(F.photo)
async def handle_photo(
    message: Message,
    bot: Bot,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Validate, compress, and recognize food from a Telegram photo."""
    if message.from_user is None:
        return
    user = await UserService(session).ensure_user(message.from_user)
    blocked = food_logging_blocked_message(user)
    if blocked:
        await message.answer(blocked)
        return
    settings_svc = create_user_settings_service(session, GoalService())
    if not await settings_svc.is_ai_analysis_enabled(user.id):
        await message.answer(AI_DISABLED_HINT)
        return
    photo = message.photo[-1]
    security = SecurityService(Path(settings.temp_media_dir))

    security.ensure_file_size(photo.file_size, settings.max_photo_bytes)

    await message.answer(PHOTO_PROCESSING_TEXT)
    original_path: Path | None = None
    compressed_path: Path | None = None
    try:
        telegram_file = await bot.get_file(photo.file_id)
        original_path = await security.download_temporary(bot, telegram_file, ".jpg")
        compressed_path = original_path.with_name(f"{original_path.stem}_compressed.jpg")
        ImageProcessor(
            max_side_px=settings.max_image_side_px,
            jpeg_quality=settings.image_jpeg_quality,
        ).validate_and_compress(original_path, compressed_path)
        result = await AIPhotoService(settings).recognize_food(compressed_path)
    finally:
        security.cleanup(original_path)
        security.cleanup(compressed_path)

    calorie_service = CalorieService()
    if message.caption and message.caption.strip():
        result = calorie_service.apply_user_text_gram_priority(
            message.caption.strip(),
            result,
        )
    result = calorie_service.apply_clarification_guards(result)
    if calorie_service.requires_blocking_clarification(result):
        await state.set_state(MealStates.waiting_for_correction)
        tz = ZoneInfo(settings.timezone)
        default_mt = infer_meal_type(datetime.now(tz))
        await state.update_data(
            photo_food_result=calorie_service.result_to_dict(result),
            clarification_mode="photo",
            pending_text_food="",
            default_meal_type=default_mt.value,
            pending_food_result_draft=None,
            photo_user_id=user.id,
            food_source=MealSource.PHOTO.value,
        )
        await message.answer(f"{TEXT_FOOD_CLARIFICATION_PREFIX}\n{result.clarification_question}")
        return
    await state.set_state(MealStates.photo_review)
    await state.update_data(
        photo_food_result=calorie_service.result_to_dict(result),
        photo_user_id=user.id,
        food_source=MealSource.PHOTO.value,
        clarification_mode=None,
        pending_food_result_draft=None,
    )
    await message.answer(
        calorie_service.format_result(result),
        reply_markup=photo_review_keyboard(),
    )


@router.callback_query(F.data == "photo_meal:confirm")
async def confirm_photo_meal(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Persist recognized food only after explicit user confirmation."""
    if await _reject_if_no_photo_draft(callback, state):
        return
    user = await UserService(session).ensure_user(callback.from_user)
    data = await state.get_data()
    result = _result_from_state(data)
    source = MealSource(data.get("food_source", MealSource.PHOTO.value))
    service = CalorieService()
    draft = service.to_meal_draft(result, source=source)
    editing_meal_id = data.get("editing_saved_meal_id")
    meal_service = MealService(
        MealRepository(session),
        MealChangeLogRepository(session),
    )
    if editing_meal_id:
        meal_id = int(editing_meal_id)
        meal_repo = MealRepository(session)
        meal_before = await meal_repo.get_user_meal(user.id, meal_id)
        if meal_before is None:
            await callback.answer(MEAL_NOT_FOUND_TEXT, show_alert=True)
            return
        before_eaten_at = meal_before.eaten_at
        before_status = meal_before.status
        before_calories = meal_before.total_calories
        before_protein_g = float(meal_before.total_protein_g or 0)
        before_fat_g = float(meal_before.total_fat_g or 0)
        before_carbs_g = float(meal_before.total_carbs_g or 0)

        meal = await meal_service.update_saved_meal(user.id, meal_id, draft)
        if meal is None:
            await callback.answer(MEAL_NOT_FOUND_TEXT, show_alert=True)
            return
        if before_status == MealStatus.CONFIRMED.value:
            await on_confirmed_meal_edited(
                session,
                settings,
                user_sql_id=user.id,
                before_eaten_at=before_eaten_at,
                before_calories=before_calories,
                before_protein_g=before_protein_g,
                before_fat_g=before_fat_g,
                before_carbs_g=before_carbs_g,
                before_status=before_status,
                after_meal=meal,
            )
    else:
        meal = await meal_service.create_draft(
            user_id=user.id,
            meal=draft,
            eaten_at=datetime.now(ZoneInfo(settings.timezone)),
        )
        await MealRepository(session).confirm(meal)
        await on_meal_confirmed(session, settings, user_sql_id=user.id, meal=meal)
    await commit_db_work_before_telegram(session)
    await state.clear()
    brief = service.format_saved_meal_brief(result)
    await send_post_action_message(
        callback.message,
        session=session,
        settings=settings,
        user_id=user.id,
        meal_brief_text=brief,
        edit_in_place=True,
    )
    meal_was_new = not bool(editing_meal_id)
    motivation = await create_motivation_service(session, settings).maybe_emit(
        user.id,
        "meal_save",
        meal_was_new=meal_was_new,
    )
    if motivation:
        await callback.message.answer(motivation, reply_markup=navigation_footer_keyboard())
    await callback.answer()


@router.callback_query(F.data == "photo_meal:cancel")
async def cancel_photo_meal(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel photo recognition without persisting anything."""
    if callback.message is None:
        await callback.answer()
        return
    data = await state.get_data()
    await state.clear()
    await callback.answer()
    if data.get("photo_food_result"):
        await _edit_or_answer_followup(
            callback,
            text=MEAL_CANCEL_FOLLOWUP,
            reply_markup=draft_cancelled_keyboard(),
        )
    else:
        await callback.message.answer(MEAL_CANCEL_FOLLOWUP, reply_markup=draft_cancelled_keyboard())


@router.callback_query(F.data == "photo_meal:quick:add")
async def photo_quick_add(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt for comma-separated name, grams, calories."""
    if await _reject_if_no_photo_draft(callback, state):
        return
    await state.set_state(MealStates.photo_editing)
    await state.update_data(photo_edit_action="add")
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(PHOTO_QUICK_ADD_TEXT)


@router.callback_query(F.data == "photo_meal:quick:delete")
async def photo_quick_delete(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt for 1-based item index to delete."""
    if await _reject_if_no_photo_draft(callback, state):
        return
    await state.set_state(MealStates.photo_editing)
    await state.update_data(photo_edit_action="delete")
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(PHOTO_QUICK_DELETE_TEXT)


@router.callback_query(F.data.startswith("photo_meal:edit:"))
async def choose_photo_edit(callback: CallbackQuery, state: FSMContext) -> None:
    """Ask user for a natural-language edit of the recognition result."""
    if await _reject_if_no_photo_draft(callback, state):
        return
    action = callback.data.rsplit(":", maxsplit=1)[1]
    if action != "flex":
        await callback.answer()
        return
    if await state.get_state() == MealStates.photo_editing.state:
        await callback.answer("Уже жду вашу правку — напишите одним сообщением.", show_alert=False)
        return
    await state.set_state(MealStates.photo_editing)
    await state.update_data(photo_edit_action=action)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(PHOTO_EDIT_FLEX_TEXT)


@router.message(MealStates.photo_editing, F.text)
async def apply_photo_edit(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Apply quick add/delete or NLP correction."""
    data = await state.get_data()
    action = str(data.get("photo_edit_action", "flex"))
    service = CalorieService()
    result = service.result_from_dict(data["photo_food_result"])
    instruction = (message.text or "").strip()
    if not instruction:
        await message.answer(PHOTO_EDIT_ERROR_TEXT)
        return

    try:
        if action == "add":
            name, grams, calories = [part.strip() for part in instruction.split(",", maxsplit=2)]
            updated = service.add_item(
                result,
                name,
                float(grams.replace(",", ".")),
                int(calories),
            )
        elif action == "delete":
            updated = service.delete_item(result, int(instruction.strip()))
        elif action == "flex":
            updated = await apply_instruction_to_food_result(
                settings,
                instruction,
                result,
                session=session,
            )
            updated = service.apply_clarification_guards(updated)
            if service.requires_blocking_clarification(updated):
                await state.set_state(MealStates.waiting_for_correction)
                await state.update_data(
                    photo_food_result=service.result_to_dict(updated),
                    clarification_mode="photo",
                    photo_edit_action=None,
                    pending_food_result_draft=None,
                )
                await message.answer(f"{TEXT_FOOD_CLARIFICATION_PREFIX}\n{updated.clarification_question}")
                return
            if not updated.items:
                await message.answer(RECOGNITION_UNCERTAIN_TEXT, reply_markup=recognition_trouble_keyboard())
                return
        else:
            await message.answer(PHOTO_EDIT_ERROR_TEXT)
            return
    except (ValueError, IndexError):
        await message.answer(PHOTO_EDIT_ERROR_TEXT)
        return
    except Exception:
        _log.exception("meal_edit_failed")
        await message.answer(PHOTO_EDIT_ERROR_TEXT)
        return

    await state.set_state(MealStates.photo_review)
    await state.update_data(
        photo_food_result=service.result_to_dict(updated),
        photo_edit_action=None,
    )
    reply = service.format_result(updated)
    if updated.needs_clarification and updated.clarification_question:
        reply = f"{reply}\n\n⚠️ {updated.clarification_question}"
    await message.answer(reply, reply_markup=photo_review_keyboard())


def _result_from_state(data: dict) -> object:
    return CalorieService().result_from_dict(data["photo_food_result"])
