from aiogram.fsm.state import State, StatesGroup


class SettingsStates(StatesGroup):
    """FSM states for editing user settings."""

    waiting_for_weight = State()
    entering_calorie_goal = State()
