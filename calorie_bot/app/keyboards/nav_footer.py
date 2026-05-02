"""Reusable bottom rows: return to logging loop from stats, trends, etc."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from calorie_bot.app.keyboards.callback_data import NavCallback


def navigation_footer_rows() -> list[list[InlineKeyboardButton]]:
    """Single strip: return to main hub (food logging stays native)."""
    return [
        [InlineKeyboardButton(text="🏠 Меню", callback_data=NavCallback.MAIN_MENU)],
    ]


def append_navigation_footer(keyboard: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    """Append sticky logging CTA + main menu without duplicating module logic elsewhere."""
    rows = list(keyboard.inline_keyboard) + navigation_footer_rows()
    return InlineKeyboardMarkup(inline_keyboard=rows)


def navigation_footer_keyboard() -> InlineKeyboardMarkup:
    """Minimal keyboard for short follow-up messages (e.g. motivation)."""
    return InlineKeyboardMarkup(inline_keyboard=navigation_footer_rows())
