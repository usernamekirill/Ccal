from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from calorie_bot.app.domain import StatsPeriod


def stats_period_keyboard(active: StatsPeriod | None = None) -> InlineKeyboardMarkup:
    """Return keyboard for selecting a statistics period."""
    day_mark = "✓ " if active == StatsPeriod.DAY else ""
    week_mark = "✓ " if active == StatsPeriod.WEEK else ""
    month_mark = "✓ " if active == StatsPeriod.MONTH else ""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{day_mark}Сегодня",
                    callback_data="stats:day",
                ),
                InlineKeyboardButton(
                    text=f"{week_mark}Неделя",
                    callback_data="stats:week",
                ),
                InlineKeyboardButton(
                    text=f"{month_mark}Месяц",
                    callback_data="stats:month",
                ),
            ]
        ]
    )
