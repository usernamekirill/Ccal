from aiogram.fsm.state import State, StatesGroup


class MealStates(StatesGroup):
    """FSM states for meal draft correction."""

    waiting_for_correction = State()
    waiting_for_weight = State()
    photo_review = State()
    photo_editing = State()
