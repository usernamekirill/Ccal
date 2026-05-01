from aiogram.fsm.state import State, StatesGroup


class MealStates(StatesGroup):
    """FSM states for meal draft correction."""

    waiting_for_correction = State()
    photo_review = State()
    photo_editing = State()
