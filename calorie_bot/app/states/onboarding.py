from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    """FSM states for collecting user goal and nutrition inputs."""

    choosing_goal = State()
    choosing_calorie_strategy = State()
    entering_manual_calories = State()
    entering_sex = State()
    entering_age = State()
    entering_height = State()
    entering_weight = State()
    choosing_activity = State()
    confirming_targets = State()
