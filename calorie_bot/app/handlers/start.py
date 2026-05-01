from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.config import Settings
from calorie_bot.app.keyboards.main_menu import primary_menu_keyboard
from calorie_bot.app.keyboards.onboarding import (
    continue_keyboard,
    goal_keyboard,
)
from calorie_bot.app.messages.ux_flow import MAIN_MENU_TITLE
from calorie_bot.app.repositories.meal_repository import MealRepository
from calorie_bot.app.repositories.profile_repository import ProfileRepository
from calorie_bot.app.repositories.stats_repository import StatsRepository
from calorie_bot.app.repositories.user_repository import UserRepository
from calorie_bot.app.services.stats_service import StatsService
from calorie_bot.app.states.onboarding import OnboardingStates
from calorie_bot.app.stats.formatting import format_today_status_line
from calorie_bot.app.texts.onboarding import (
    COMPLETED_WELCOME,
    CONTINUE_PROMPT,
    GOAL_PROMPT,
    WELCOME,
)

router = Router(name="start")

_MEAL_IDLE = timedelta(hours=24)


async def _meal_logging_nudge(
    meal_repo: MealRepository,
    settings: Settings,
    user_id: int,
) -> str:
    """Suggest logging when the user has no recent meal (or no meals at all)."""
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    last = await meal_repo.latest_confirmed_eaten_at(user_id)
    if last is None:
        if await meal_repo.count_confirmed_meals(user_id) == 0:
            return "\n\n💡 Готов записать первый приём? Отправь фото, голос или текст."
        return ""
    le = last if last.tzinfo else last.replace(tzinfo=tz)
    le_local = le.astimezone(tz)
    if now - le_local > _MEAL_IDLE:
        return "\n\n💡 Хочешь добавить приём пищи? Давно ничего не логировали."
    return ""


@router.message(CommandStart())
async def handle_start(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Welcome a new user and introduce onboarding."""
    if message.from_user is None:
        return

    user = await UserRepository(session).upsert_telegram_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    current_state = await state.get_state()
    if user.onboarding_completed:
        await state.clear()
        stats = StatsService(
            stats_repository=StatsRepository(session),
            profile_repository=ProfileRepository(session),
            default_timezone=settings.timezone,
        )
        view = await stats.today_view(user.id)
        line = format_today_status_line(view)
        nudge = await _meal_logging_nudge(MealRepository(session), settings, user.id)
        text = f"{line}\n\n{COMPLETED_WELCOME}{nudge}\n\n{MAIN_MENU_TITLE}"
        await message.answer(text, reply_markup=primary_menu_keyboard())
        return
    if current_state:
        await message.answer(CONTINUE_PROMPT, reply_markup=continue_keyboard())
        return

    await state.clear()
    await state.set_state(OnboardingStates.choosing_goal)
    user.onboarding_status = "in_progress"
    await message.answer(f"{WELCOME}\n\n{GOAL_PROMPT}", reply_markup=goal_keyboard())
