"""Hub menu: stats and settings only — food is sent natively (photo / voice / text)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from calorie_bot.app.keyboards.callback_data import NavCallback


def primary_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню: сегодня, тренд, цель, настройки, помощь — без лишних режимов."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Сегодня", callback_data="today:list"),
                InlineKeyboardButton(text="📈 Тренд", callback_data="trend:7"),
            ],
            [
                InlineKeyboardButton(text="🎯 Цель", callback_data="settings:goal"),
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings:main"),
            ],
            [InlineKeyboardButton(text="❓ Помощь", callback_data=NavCallback.HELP)],
        ]
    )
