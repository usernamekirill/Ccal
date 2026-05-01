from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def goal_keyboard() -> InlineKeyboardMarkup:
    """Return goal selection keyboard for onboarding."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Похудеть", callback_data="onboarding:goal:lose_weight")],
            [
                InlineKeyboardButton(
                    text="Поддерживать вес",
                    callback_data="onboarding:goal:maintain_weight",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Набрать массу",
                    callback_data="onboarding:goal:gain_weight",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Просто считать калории",
                    callback_data="onboarding:goal:track_calories",
                )
            ],
        ]
    )


def calorie_strategy_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard for choosing calorie target strategy."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Укажу сам", callback_data="onboarding:calories:manual")],
            [
                InlineKeyboardButton(
                    text="Рассчитать",
                    callback_data="onboarding:calories:calculate",
                )
            ],
            [InlineKeyboardButton(text="Пропустить", callback_data="onboarding:calories:skip")],
        ]
    )


def sex_keyboard() -> InlineKeyboardMarkup:
    """Return sex selection keyboard for onboarding."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Женский", callback_data="onboarding:sex:female")],
            [InlineKeyboardButton(text="Мужской", callback_data="onboarding:sex:male")],
            [InlineKeyboardButton(text="Пропустить", callback_data="onboarding:skip")],
        ]
    )


def activity_keyboard() -> InlineKeyboardMarkup:
    """Return activity level keyboard for onboarding."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Мало двигаюсь",
                    callback_data="onboarding:activity:sedentary",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Легкая активность",
                    callback_data="onboarding:activity:light",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Тренируюсь 3-4 раза",
                    callback_data="onboarding:activity:moderate",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Активный режим",
                    callback_data="onboarding:activity:active",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Очень активный",
                    callback_data="onboarding:activity:very_active",
                )
            ],
            [InlineKeyboardButton(text="Пропустить", callback_data="onboarding:skip")],
        ]
    )


def targets_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Return confirmation keyboard for calculated nutrition targets."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сохранить", callback_data="onboarding:targets:confirm")],
            [
                InlineKeyboardButton(
                    text="Начать заново",
                    callback_data="onboarding:targets:restart",
                )
            ],
        ]
    )


def skip_keyboard() -> InlineKeyboardMarkup:
    """Return a one-button skip keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Пропустить", callback_data="onboarding:skip")]]
    )


def continue_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard for resuming or restarting onboarding."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Продолжить", callback_data="onboarding:continue")],
            [InlineKeyboardButton(text="Начать заново", callback_data="onboarding:restart")],
        ]
    )
