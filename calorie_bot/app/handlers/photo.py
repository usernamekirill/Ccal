from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.ai.photo_service import AIPhotoService
from calorie_bot.app.config import Settings
from calorie_bot.app.database.telegram_safe_commit import commit_db_work_before_telegram
from calorie_bot.app.domain import MealSource, MealStatus, MealType
from calorie_bot.app.keyboards.confirmation import draft_cancelled_keyboard
from calorie_bot.app.keyboards.meal import meal_type_keyboard, photo_review_keyboard
from calorie_bot.app.keyboards.nav_footer import navigation_footer_keyboard
from calorie_bot.app.messages.texts import (
    MEAL_CANCELLED_TEXT,
    MEAL_NOT_FOUND_TEXT,
    PHOTO_ADD_ITEM_TEXT,
    PHOTO_DELETE_ITEM_TEXT,
    PHOTO_EDIT_CALORIES_TEXT,
    PHOTO_EDIT_ERROR_TEXT,
    PHOTO_EDIT_GRAMS_TEXT,
    PHOTO_EDIT_NAME_TEXT,
    PHOTO_PROCESSING_TEXT,
)
from calorie_bot.app.post_action_message import send_post_action_message
from calorie_bot.app.repositories.meal_change_log_repository import MealChangeLogRepository
from calorie_bot.app.repositories.meal_repository import MealRepository
from calorie_bot.app.services.calorie_service import CalorieService
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

router = Router(name="photo")


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
    await state.set_state(MealStates.photo_review)
    await state.update_data(
        photo_food_result=calorie_service.result_to_dict(result),
        photo_user_id=user.id,
        food_source=MealSource.PHOTO.value,
    )
    await message.answer(
        calorie_service.format_result(result),
        reply_markup=photo_review_keyboard(),
    )


@router.callback_query(F.data == "photo_meal:confirm", MealStates.photo_review)
async def confirm_photo_meal(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Persist recognized food only after explicit user confirmation."""
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


@router.callback_query(F.data == "photo_meal:cancel", MealStates.photo_review)
async def cancel_photo_meal(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel photo recognition without persisting anything."""
    await state.clear()
    await callback.message.edit_text(MEAL_CANCELLED_TEXT, reply_markup=draft_cancelled_keyboard())
    await callback.answer()


@router.callback_query(F.data == "meal:voice", MealStates.photo_review)
async def prompt_voice_correction(callback: CallbackQuery) -> None:
    """Tell the user how to correct the current draft by voice."""
    await callback.message.answer(
        "Запиши голосом, что изменить. Например: риса было 120 грамм и добавь соус.",
        reply_markup=navigation_footer_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("photo_meal:edit:"), MealStates.photo_review)
async def choose_photo_edit(callback: CallbackQuery, state: FSMContext) -> None:
    """Ask user for a specific photo result edit."""
    action = callback.data.rsplit(":", maxsplit=1)[1]
    await state.set_state(MealStates.photo_editing)
    await state.update_data(photo_edit_action=action)
    prompts = {
        "name": PHOTO_EDIT_NAME_TEXT,
        "grams": PHOTO_EDIT_GRAMS_TEXT,
        "calories": PHOTO_EDIT_CALORIES_TEXT,
        "add": PHOTO_ADD_ITEM_TEXT,
        "delete": PHOTO_DELETE_ITEM_TEXT,
    }
    await callback.message.answer(prompts[action])
    await callback.answer()


@router.callback_query(F.data == "food:meal_type", MealStates.photo_review)
async def choose_meal_type(callback: CallbackQuery) -> None:
    """Ask user to choose meal type for the current draft."""
    await callback.message.answer("Выберите тип приема пищи:", reply_markup=meal_type_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("food:meal_type:"), MealStates.photo_review)
async def update_meal_type(callback: CallbackQuery, state: FSMContext) -> None:
    """Update meal type in current FSM draft."""
    meal_type = MealType(callback.data.rsplit(":", maxsplit=1)[1])
    service = CalorieService()
    result = service.result_from_dict((await state.get_data())["photo_food_result"])
    updated = service.update_meal_type(result, meal_type)
    await state.update_data(photo_food_result=service.result_to_dict(updated))
    await callback.message.edit_text(
        service.format_result(updated),
        reply_markup=photo_review_keyboard(),
    )
    await callback.answer()


@router.message(MealStates.photo_editing)
async def apply_photo_edit(message: Message, state: FSMContext) -> None:
    """Apply a user edit to the FSM-stored photo recognition result."""
    data = await state.get_data()
    action = str(data.get("photo_edit_action"))
    service = CalorieService()
    result = service.result_from_dict(data["photo_food_result"])

    try:
        updated = _apply_edit(service, result, action, message.text or "")
    except (ValueError, IndexError):
        await message.answer(PHOTO_EDIT_ERROR_TEXT)
        return

    await state.set_state(MealStates.photo_review)
    await state.update_data(
        photo_food_result=service.result_to_dict(updated),
        photo_edit_action=None,
    )
    await message.answer(service.format_result(updated), reply_markup=photo_review_keyboard())


def _result_from_state(data: dict) -> object:
    return CalorieService().result_from_dict(data["photo_food_result"])


def _apply_edit(service: CalorieService, result, action: str, text: str):
    if action == "name":
        index, value = _split_index_value(text)
        return service.update_name(result, index, value)
    if action == "grams":
        index, value = _split_index_value(text)
        return service.update_grams(result, index, float(value.replace(",", ".")))
    if action == "calories":
        index, value = _split_index_value(text)
        return service.update_calories(result, index, int(value))
    if action == "delete":
        return service.delete_item(result, int(text.strip()))
    if action == "add":
        name, grams, calories = [part.strip() for part in text.split(",", maxsplit=2)]
        return service.add_item(result, name, float(grams.replace(",", ".")), int(calories))
    raise ValueError("unsupported_photo_edit_action")


def _split_index_value(text: str) -> tuple[int, str]:
    index, value = text.strip().split(maxsplit=1)
    return int(index), value
