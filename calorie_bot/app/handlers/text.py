from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.config import Settings
from calorie_bot.app.keyboards.meal import meal_confirmation_keyboard
from calorie_bot.app.messages.templates import meal_item_lines
from calorie_bot.app.messages.texts import render_meal_draft_text
from calorie_bot.app.repositories.meal_repository import MealRepository
from calorie_bot.app.services.correction_service import CorrectionService
from calorie_bot.app.services.meal_service import MealService, meal_model_to_draft
from calorie_bot.app.services.user_service import UserService

router = Router(name="text")


@router.message(F.text)
async def handle_text_meal(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Create or update a meal draft from user text."""
    if message.from_user is None or message.text is None:
        return
    if message.text.startswith("/"):
        return

    user = await UserService(session).ensure_user(message.from_user)
    meal_service = MealService(MealRepository(session))
    latest = await meal_service.latest_draft(user.id)
    current = meal_model_to_draft(latest) if latest else None
    draft = CorrectionService().apply_text(current, message.text)

    if latest:
        await meal_service.apply_draft_update(latest, draft)
    else:
        await meal_service.create_draft(
            user_id=user.id,
            meal=draft,
            eaten_at=datetime.now(ZoneInfo(settings.timezone)),
        )

    await message.answer(
        render_meal_draft_text(
            items=meal_item_lines(draft),
            total_calories=draft.total_calories,
            confidence=draft.confidence,
            notes=draft.notes,
        ),
        reply_markup=meal_confirmation_keyboard(),
    )
