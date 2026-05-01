"""Keyboards after meal confirmation, cancel, or whenever the user needs a clear next step."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from calorie_bot.app.keyboards.callback_data import NavCallback


def after_meal_saved_keyboard() -> InlineKeyboardMarkup:
    """Primary CTAs after a meal is saved (sticky first row: add food)."""
    add_food = NavCallback.ADD_FOOD
    voice = NavCallback.ADD_VOICE_HINT
    text_ = NavCallback.ADD_TEXT_HINT
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📸 Добавить еду", callback_data=add_food)],
            [InlineKeyboardButton(text="🎙 Сказать голосом", callback_data=voice)],
            [InlineKeyboardButton(text="✍️ Ввести текстом", callback_data=text_)],
            [InlineKeyboardButton(text="📊 Посмотреть статистику", callback_data="stats:day")],
            [InlineKeyboardButton(text="📅 Сегодня", callback_data="today:list")],
        ]
    )


def draft_cancelled_keyboard() -> InlineKeyboardMarkup:
    """Same navigation as after save so cancel is not a dead end."""
    return after_meal_saved_keyboard()
