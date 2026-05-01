"""Inline keyboard for trend window length."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def trend_window_keyboard(active_days: int | None = None) -> InlineKeyboardMarkup:
    """Return 7 / 14 / 30 day selectors; optional checkmark on the active window."""
    def label(days: int, title: str) -> str:
        mark = "✓ " if active_days == days else ""
        return f"{mark}{title}"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=label(7, "7 дней"), callback_data="trend:7"),
                InlineKeyboardButton(text=label(14, "14 дней"), callback_data="trend:14"),
                InlineKeyboardButton(text=label(30, "30 дней"), callback_data="trend:30"),
            ]
        ]
    )
