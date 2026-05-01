"""Action-driven main menu (max 5 primary actions)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from calorie_bot.app.keyboards.callback_data import NavCallback


def primary_menu_keyboard() -> InlineKeyboardMarkup:
    """Return the post-onboarding hub: logging first, then day view, progress, goal, settings."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📸 Добавить еду", callback_data=NavCallback.ADD_FOOD)],
            [InlineKeyboardButton(text="📊 Сегодня", callback_data="today:list")],
            [InlineKeyboardButton(text="📈 Прогресс", callback_data="trend:7")],
            [InlineKeyboardButton(text="🎯 Цель", callback_data="settings:goal")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings:main")],
        ]
    )
