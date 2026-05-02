"""Keyboards after meal confirmation, cancel, or whenever the user needs a clear next step."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from calorie_bot.app.keyboards.callback_data import NavCallback


def after_meal_saved_keyboard() -> InlineKeyboardMarkup:
    """Hub actions after save — no separate photo/voice/text mode buttons."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Сегодня", callback_data="today:list"),
                InlineKeyboardButton(text="📈 Тренд", callback_data="trend:7"),
            ],
            [InlineKeyboardButton(text="🏠 Меню", callback_data=NavCallback.MAIN_MENU)],
        ]
    )


def draft_cancelled_keyboard() -> InlineKeyboardMarkup:
    """After cancel — simple exit, no mode-selection dead end."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Сегодня", callback_data="today:list")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data=NavCallback.MAIN_MENU)],
        ]
    )


def recognition_trouble_keyboard() -> InlineKeyboardMarkup:
    """When recognition failed or model is unsure — menu + help, no input-mode grid."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏠 Меню", callback_data=NavCallback.MAIN_MENU),
                InlineKeyboardButton(text="❓ Помощь", callback_data=NavCallback.HELP),
            ],
        ]
    )


def help_screen_keyboard() -> InlineKeyboardMarkup:
    """End of help screen."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Меню", callback_data=NavCallback.MAIN_MENU)],
        ]
    )
