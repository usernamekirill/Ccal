"""Telegram handlers for preferences, targets, and verified data deletion."""

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.config import Settings
from calorie_bot.app.database.models import User as AppUser
from calorie_bot.app.domain import MeasurementUnit
from calorie_bot.app.keyboards.nav_footer import append_navigation_footer
from calorie_bot.app.keyboards.settings import (
    back_to_settings_keyboard,
    delete_confirm_keyboard,
    main_settings_keyboard,
    profile_restart_keyboard,
    resolve_timezone,
    timezone_keyboard,
    units_keyboard,
)
from calorie_bot.app.repositories.profile_repository import ProfileRepository
from calorie_bot.app.repositories.settings_repository import SettingsRepository
from calorie_bot.app.repositories.stats_repository import StatsRepository
from calorie_bot.app.services.goal_service import GoalService
from calorie_bot.app.services.stats_service import StatsService
from calorie_bot.app.services.user_service import UserService
from calorie_bot.app.services.user_settings_service import create_user_settings_service
from calorie_bot.app.states.settings import SettingsStates
from calorie_bot.app.stats.formatting import format_today_status_line
from calorie_bot.app.texts import settings as settings_texts

router = Router(name="settings")


async def _message_main_content(
    session: AsyncSession,
    user_internal_id: int,
    settings: Settings,
) -> tuple[str, object]:
    """Build overview text and keyboard for the settings hub."""
    stats = StatsService(
        stats_repository=StatsRepository(session),
        profile_repository=ProfileRepository(session),
        default_timezone=settings.timezone,
    )
    line = format_today_status_line(await stats.today_view(user_internal_id))
    profile = await ProfileRepository(session).get_by_user_id(user_internal_id)
    row = await SettingsRepository(session).get_by_user_id(user_internal_id)
    notifications = True if row is None else bool(row.notifications_enabled)
    motivation = True if row is None else bool(row.motivation_messages_enabled)
    ai_on = True if row is None else bool(row.ai_analysis_enabled)
    unit = row.measurement_unit if row else MeasurementUnit.METRIC.value
    text = (
        f"{line}\n\n"
        + settings_texts.main_screen_text(
        goal_key=profile.goal if profile else None,
        daily_calorie_target=profile.daily_calorie_target if profile else None,
        protein_g=profile.daily_protein_target_g if profile else None,
        fat_g=profile.daily_fat_target_g if profile else None,
        carbs_g=profile.daily_carbs_target_g if profile else None,
        profile_timezone=profile.timezone if profile else None,
        settings_timezone=row.timezone if row else None,
        notifications_on=notifications,
        motivation_on=motivation,
        ai_on=ai_on,
        measurement_unit=unit,
        )
    )
    keyboard = append_navigation_footer(
        main_settings_keyboard(
            notifications_on=notifications,
            motivation_on=motivation,
            ai_on=ai_on,
        ),
    )
    return text, keyboard


async def _require_profile_reply(
    message: Message,
    session: AsyncSession,
    telegram_user: TelegramUser,
) -> AppUser | None:
    """Return internal user if profile exists; otherwise notify and return None."""
    user = await UserService(session).ensure_user(telegram_user)
    profile = await ProfileRepository(session).get_by_user_id(user.id)
    if profile is None:
        await message.answer(settings_texts.SETTINGS_NO_PROFILE)
        return None
    return user


@router.message(Command("settings"))
async def settings_command(message: Message, session: AsyncSession, settings: Settings) -> None:
    """Open the settings overview."""
    if message.from_user is None:
        return
    user = await _require_profile_reply(message, session, message.from_user)
    if user is None:
        return
    text, keyboard = await _message_main_content(session, user.id, settings)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "settings:main")
async def settings_main(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    """Return to the main settings panel."""
    await state.clear()
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    profile = await ProfileRepository(session).get_by_user_id(user.id)
    if profile is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    text, keyboard = await _message_main_content(session, user.id, settings)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "settings:goal")
async def settings_goal_start(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Ask for a new calorie target."""
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    if await ProfileRepository(session).get_by_user_id(user.id) is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    await state.set_state(SettingsStates.entering_calorie_goal)
    await callback.message.edit_text(
        settings_texts.CALORIE_GOAL_PROMPT,
        reply_markup=back_to_settings_keyboard(),
    )
    await callback.answer()


@router.message(StateFilter(SettingsStates.entering_calorie_goal), F.text)
async def settings_goal_save(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
) -> None:
    """Parse calorie goal and persist with progress sync."""
    if message.from_user is None or message.text is None:
        return
    user = await UserService(session).ensure_user(message.from_user)
    raw = message.text.strip().replace(" ", "")
    if not raw.isdigit():
        await message.answer(settings_texts.INVALID_CALORIE_NUMBER)
        return
    calories = int(raw)
    service = create_user_settings_service(session, GoalService())
    try:
        await service.set_daily_calorie_target(user.id, calories)
    except ValueError:
        await message.answer(settings_texts.CALORIE_OUT_OF_RANGE)
        return
    await state.clear()
    await message.answer(settings_texts.CALORIE_GOAL_SAVED)
    text, keyboard = await _message_main_content(session, user.id, settings)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "settings:timezone")
async def settings_timezone_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show timezone picker."""
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    if await ProfileRepository(session).get_by_user_id(user.id) is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    await callback.message.edit_text(
        settings_texts.TIMEZONE_HEADING,
        reply_markup=timezone_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:tzpick:"))
async def settings_timezone_pick(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Apply a timezone from the indexed list."""
    if callback.data is None or callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    if await ProfileRepository(session).get_by_user_id(user.id) is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    idx_raw = callback.data.split(":")[-1]
    try:
        idx = int(idx_raw)
    except ValueError:
        await callback.answer("Неверный выбор", show_alert=True)
        return
    iana = resolve_timezone(idx)
    if iana is None:
        await callback.answer("Неверный выбор", show_alert=True)
        return
    service = create_user_settings_service(session, GoalService())
    try:
        await service.update_timezone(user.id, iana)
    except ValueError:
        await callback.answer("Часовой пояс не поддерживается", show_alert=True)
        return
    await callback.answer(settings_texts.TIMEZONE_SAVED)
    text, keyboard = await _message_main_content(session, user.id, settings)
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "settings:units")
async def settings_units_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show unit preference keyboard."""
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    if await ProfileRepository(session).get_by_user_id(user.id) is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    await callback.message.edit_text(
        settings_texts.UNITS_HEADING,
        reply_markup=units_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.in_({"settings:unit:metric", "settings:unit:imperial"}))
async def settings_units_save(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Persist metric/imperial flag."""
    if callback.data is None or callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    if await ProfileRepository(session).get_by_user_id(user.id) is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    unit = (
        MeasurementUnit.METRIC
        if callback.data == "settings:unit:metric"
        else MeasurementUnit.IMPERIAL
    )
    service = create_user_settings_service(session, GoalService())
    await service.set_measurement_unit(user.id, unit)
    await callback.answer("Сохранено")
    text, keyboard = await _message_main_content(session, user.id, settings)
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(
    F.data.in_(
        {
            "settings:toggle:notifications",
            "settings:toggle:motivation",
            "settings:toggle:ai",
        },
    ),
)
async def settings_toggles(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Flip notification, motivation, or AI flags."""
    if callback.data is None or callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    if await ProfileRepository(session).get_by_user_id(user.id) is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    row = await SettingsRepository(session).get_or_create(user.id)
    service = create_user_settings_service(session, GoalService())
    if callback.data == "settings:toggle:notifications":
        await service.set_notifications_enabled(user.id, not row.notifications_enabled)
    elif callback.data == "settings:toggle:motivation":
        await service.set_motivation_enabled(user.id, not row.motivation_messages_enabled)
    else:
        await service.set_ai_analysis_enabled(user.id, not row.ai_analysis_enabled)
    await callback.answer("Сохранено")
    text, keyboard = await _message_main_content(session, user.id, settings)
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "settings:recalc")
async def settings_recalc(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Recompute TDEE/macros when full anthropometrics exist."""
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    if await ProfileRepository(session).get_by_user_id(user.id) is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    service = create_user_settings_service(session, GoalService())
    ok = await service.recalculate_targets_from_profile(user.id)
    if not ok:
        await callback.message.answer(settings_texts.RECALC_NEEDS_FULL_PROFILE)
        await callback.answer()
        return
    await callback.answer(settings_texts.RECALC_OK)
    text, keyboard = await _message_main_content(session, user.id, settings)
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "settings:profile:edit")
async def settings_profile_edit(callback: CallbackQuery, session: AsyncSession) -> None:
    """Point users at onboarding restart for full profile changes."""
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    if await ProfileRepository(session).get_by_user_id(user.id) is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    await callback.message.edit_text(
        settings_texts.PROFILE_EDIT_INTRO,
        reply_markup=profile_restart_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:data:warn")
async def settings_data_warn(callback: CallbackQuery, session: AsyncSession) -> None:
    """First step of destructive delete."""
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    if await ProfileRepository(session).get_by_user_id(user.id) is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    await callback.message.edit_text(
        settings_texts.DATA_DELETE_WARN,
        reply_markup=delete_confirm_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:data:cancel")
async def settings_data_cancel(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Abort account data removal."""
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    if await ProfileRepository(session).get_by_user_id(user.id) is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    await callback.answer(settings_texts.DATA_DELETE_CANCELLED)
    text, keyboard = await _message_main_content(session, user.id, settings)
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "settings:data:confirm")
async def settings_data_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Hard-delete all persisted rows for this account after explicit confirm."""
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await UserService(session).ensure_user(callback.from_user)
    internal_id = user.id
    service = create_user_settings_service(session, GoalService())
    await service.purge_all_data(internal_id)
    await state.clear()
    await callback.message.edit_text(settings_texts.DATA_DELETED_OK, reply_markup=None)
    await callback.answer()
