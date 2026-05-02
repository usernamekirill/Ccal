"""Helpers for treating native Telegram messages as food input or draft edits."""

from aiogram.fsm.context import FSMContext

from calorie_bot.app.states.meal import MealStates


async def has_active_photo_draft_fsm(state: FSMContext) -> bool:
    """True when a Telegram review/edit draft is open (preview or awaiting typed correction)."""
    st = await state.get_state()
    return st in (MealStates.photo_review.state, MealStates.photo_editing.state)


async def has_photo_food_result_data(state: FSMContext) -> bool:
    """True when FSM data holds a serialized ``photo_food_result``."""
    data = await state.get_data()
    return bool(data.get("photo_food_result"))


async def should_treat_native_message_as_draft_edit(state: FSMContext) -> bool:
    """Voice/text should refine the current draft instead of starting a new meal."""
    if not await has_active_photo_draft_fsm(state):
        return False
    return await has_photo_food_result_data(state)
