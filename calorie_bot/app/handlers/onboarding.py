from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.config import Settings
from calorie_bot.app.domain import FitnessGoal
from calorie_bot.app.keyboards.main_menu import primary_menu_keyboard
from calorie_bot.app.keyboards.onboarding import (
    activity_keyboard,
    calorie_strategy_keyboard,
    goal_keyboard,
    sex_keyboard,
    skip_keyboard,
    targets_confirmation_keyboard,
)
from calorie_bot.app.repositories.profile_repository import ProfileRepository, WeightLogRepository
from calorie_bot.app.repositories.settings_repository import SettingsRepository
from calorie_bot.app.repositories.user_repository import UserRepository
from calorie_bot.app.services.goal_service import GoalService
from calorie_bot.app.services.onboarding_service import OnboardingService, build_goal_input_from_fsm
from calorie_bot.app.states.onboarding import OnboardingStates
from calorie_bot.app.texts import onboarding as texts

router = Router(name="onboarding")


@router.callback_query(F.data == "onboarding:continue")
async def continue_onboarding(callback: CallbackQuery) -> None:
    """Acknowledge onboarding continuation."""
    await callback.answer()
    await callback.message.answer("Продолжаем 🙂 Ответь на последний вопрос выше.")


@router.callback_query(F.data == "onboarding:restart")
async def restart_onboarding(callback: CallbackQuery, state: FSMContext) -> None:
    """Restart onboarding from goal selection."""
    await _start_goal_selection(callback, state, texts.RESTARTED)


@router.callback_query(F.data.startswith("onboarding:goal:"), OnboardingStates.choosing_goal)
async def handle_goal(callback: CallbackQuery, state: FSMContext) -> None:
    """Store selected goal and ask how to set calories."""
    goal = _callback_value(callback.data)
    await state.update_data(goal=goal)
    await state.set_state(OnboardingStates.choosing_calorie_strategy)
    await callback.message.edit_text(
        texts.CALORIE_STRATEGY_PROMPT,
        reply_markup=calorie_strategy_keyboard(),
    )
    await callback.answer()


@router.callback_query(
    F.data.startswith("onboarding:calories:"),
    OnboardingStates.choosing_calorie_strategy,
)
async def handle_calorie_strategy(callback: CallbackQuery, state: FSMContext) -> None:
    """Branch onboarding into manual, calculated, or skipped calorie goal."""
    strategy = _callback_value(callback.data)
    if strategy == "manual":
        await state.set_state(OnboardingStates.entering_manual_calories)
        await callback.message.edit_text(texts.MANUAL_CALORIES_PROMPT)
    elif strategy == "calculate":
        await state.set_state(OnboardingStates.entering_sex)
        await callback.message.edit_text(texts.SEX_PROMPT, reply_markup=sex_keyboard())
    else:
        await state.update_data(daily_calorie_target=None)
        await state.set_state(OnboardingStates.confirming_targets)
        await callback.message.edit_text(
            texts.render_targets(calories=None),
            reply_markup=targets_confirmation_keyboard(),
        )
    await callback.answer()


@router.message(OnboardingStates.entering_manual_calories)
async def handle_manual_calories(message: Message, state: FSMContext) -> None:
    """Store manually entered daily calories."""
    calories = _parse_int(message.text)
    if calories is None:
        await message.answer(texts.INVALID_NUMBER)
        return
    await state.update_data(daily_calorie_target=calories)
    await state.set_state(OnboardingStates.confirming_targets)
    await message.answer(
        texts.render_targets(calories=calories),
        reply_markup=targets_confirmation_keyboard(),
    )


@router.callback_query(F.data.startswith("onboarding:sex:"), OnboardingStates.entering_sex)
async def handle_sex(callback: CallbackQuery, state: FSMContext) -> None:
    """Store sex and ask for age."""
    await state.update_data(sex=_callback_value(callback.data))
    await state.set_state(OnboardingStates.entering_age)
    await callback.message.edit_text(texts.AGE_PROMPT, reply_markup=skip_keyboard())
    await callback.answer()


@router.message(OnboardingStates.entering_age)
async def handle_age(message: Message, state: FSMContext) -> None:
    """Store age and ask for height."""
    age = _parse_int(message.text)
    if age is None:
        await message.answer(texts.INVALID_NUMBER)
        return
    await state.update_data(age=age)
    await state.set_state(OnboardingStates.entering_height)
    await message.answer(texts.HEIGHT_PROMPT, reply_markup=skip_keyboard())


@router.message(OnboardingStates.entering_height)
async def handle_height(message: Message, state: FSMContext) -> None:
    """Store height and ask for weight."""
    height_cm = _parse_float(message.text)
    if height_cm is None:
        await message.answer(texts.INVALID_NUMBER)
        return
    await state.update_data(height_cm=height_cm)
    await state.set_state(OnboardingStates.entering_weight)
    await message.answer(texts.WEIGHT_PROMPT, reply_markup=skip_keyboard())


@router.message(OnboardingStates.entering_weight)
async def handle_weight(message: Message, state: FSMContext) -> None:
    """Store weight and ask for activity level."""
    weight_kg = _parse_float(message.text)
    if weight_kg is None:
        await message.answer(texts.INVALID_NUMBER)
        return
    await state.update_data(weight_kg=weight_kg)
    await state.set_state(OnboardingStates.choosing_activity)
    await message.answer(texts.ACTIVITY_PROMPT, reply_markup=activity_keyboard())


@router.callback_query(
    F.data.startswith("onboarding:activity:"),
    OnboardingStates.choosing_activity,
)
async def handle_activity(callback: CallbackQuery, state: FSMContext) -> None:
    """Calculate targets and ask user to confirm."""
    await state.update_data(activity_level=_callback_value(callback.data))
    data = await state.get_data()
    if not _can_calculate_targets(data):
        await state.set_state(OnboardingStates.confirming_targets)
        await callback.message.edit_text(
            texts.CALCULATION_NEEDS_DATA,
            reply_markup=targets_confirmation_keyboard(),
        )
        await callback.answer()
        return

    targets = GoalService().calculate_daily_targets(build_goal_input_from_fsm(data))
    await state.update_data(
        daily_calorie_target=targets.daily_calorie_target,
        calculated_targets=targets,
    )
    await state.set_state(OnboardingStates.confirming_targets)
    await callback.message.edit_text(
        texts.render_targets(
            calories=targets.daily_calorie_target,
            protein_g=targets.daily_protein_target_g,
            fat_g=targets.daily_fat_target_g,
            carbs_g=targets.daily_carbs_target_g,
        ),
        reply_markup=targets_confirmation_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "onboarding:skip")
async def skip_current_question(callback: CallbackQuery, state: FSMContext) -> None:
    """Skip the current onboarding question and continue safely."""
    current_state = await state.get_state()
    if current_state == OnboardingStates.entering_sex.state:
        await state.update_data(sex=None)
        await state.set_state(OnboardingStates.entering_age)
        await callback.message.edit_text(texts.AGE_PROMPT, reply_markup=skip_keyboard())
    elif current_state == OnboardingStates.entering_age.state:
        await state.update_data(age=None)
        await state.set_state(OnboardingStates.entering_height)
        await callback.message.edit_text(texts.HEIGHT_PROMPT, reply_markup=skip_keyboard())
    elif current_state == OnboardingStates.entering_height.state:
        await state.update_data(height_cm=None)
        await state.set_state(OnboardingStates.entering_weight)
        await callback.message.edit_text(texts.WEIGHT_PROMPT, reply_markup=skip_keyboard())
    elif current_state == OnboardingStates.entering_weight.state:
        await state.update_data(weight_kg=None)
        await state.set_state(OnboardingStates.choosing_activity)
        await callback.message.edit_text(texts.ACTIVITY_PROMPT, reply_markup=activity_keyboard())
    elif current_state == OnboardingStates.choosing_activity.state:
        await state.update_data(activity_level=None)
        await state.set_state(OnboardingStates.confirming_targets)
        await callback.message.edit_text(
            texts.CALCULATION_NEEDS_DATA,
            reply_markup=targets_confirmation_keyboard(),
        )
    await callback.answer(texts.SKIPPED)


@router.callback_query(F.data == "onboarding:targets:restart", OnboardingStates.confirming_targets)
async def restart_targets(callback: CallbackQuery, state: FSMContext) -> None:
    """Restart onboarding target collection."""
    await _start_goal_selection(callback, state, texts.RESTARTED)


@router.callback_query(F.data == "onboarding:targets:confirm", OnboardingStates.confirming_targets)
async def confirm_targets(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Persist onboarding settings and show the main menu."""
    user = await UserRepository(session).upsert_telegram_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    service = _onboarding_service(session)
    data = await state.get_data()

    if service.can_calculate_targets(data):
        await service.complete_onboarding(
            user=user,
            goal_input=build_goal_input_from_fsm(data),
            timezone=settings.timezone,
        )
    elif data.get("daily_calorie_target") is not None:
        await service.complete_with_manual_calories(
            user=user,
            goal=FitnessGoal(str(data["goal"])),
            daily_calorie_target=int(data["daily_calorie_target"]),
            timezone=settings.timezone,
        )
    else:
        await service.complete_with_partial_data(user=user, data=data, timezone=settings.timezone)

    await state.clear()
    await callback.message.edit_text(
        f"{texts.FINISHED}\n\n{texts.render_main_menu()}",
        reply_markup=primary_menu_keyboard(),
    )
    await callback.answer()


async def _start_goal_selection(callback: CallbackQuery, state: FSMContext, text: str) -> None:
    await state.clear()
    await state.set_state(OnboardingStates.choosing_goal)
    await callback.message.edit_text(text, reply_markup=goal_keyboard())
    await callback.answer()


def _onboarding_service(session: AsyncSession) -> OnboardingService:
    return OnboardingService(
        profile_repository=ProfileRepository(session),
        weight_log_repository=WeightLogRepository(session),
        settings_repository=SettingsRepository(session),
        goal_service=GoalService(),
    )


def _can_calculate_targets(data: dict[str, object]) -> bool:
    required = ("goal", "sex", "age", "height_cm", "weight_kg", "activity_level")
    return all(data.get(key) is not None for key in required)


def _callback_value(data: str | None) -> str:
    return data.rsplit(":", maxsplit=1)[1] if data else ""


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value.strip())
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value.strip().replace(",", "."))
    except ValueError:
        return None
    return parsed if parsed > 0 else None
