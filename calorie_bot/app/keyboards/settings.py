from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

_TIMEZONES: tuple[tuple[str, str], ...] = (
    ("Europe/Moscow", "🇷🇺 Москва"),
    ("Europe/Kaliningrad", "🇷🇺 Калининград"),
    ("Asia/Yekaterinburg", "🇷🇺 Екатеринбург"),
    ("Asia/Novosibirsk", "🇷🇺 Новосибирск"),
    ("Asia/Vladivostok", "🇷🇺 Владивосток"),
    ("Europe/London", "🇬🇧 Лондон"),
    ("Europe/Berlin", "🇩🇪 Берлин"),
    ("UTC", "🌍 UTC"),
    ("America/New_York", "🇺🇸 Нью-Йорк"),
)


def main_settings_keyboard(
    *,
    notifications_on: bool,
    motivation_on: bool,
    ai_on: bool,
) -> InlineKeyboardMarkup:
    """Primary settings menu."""
    notif_label = "🔔 Уведомления: вкл." if notifications_on else "🔕 Уведомления: выкл."
    mot_label = "💪 Мотивация: вкл." if motivation_on else "💬 Мотивация: выкл."
    ai_label = "🤖 AI-анализ: вкл." if ai_on else "⛔ AI-анализ: выкл."
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Цель калорий", callback_data="settings:goal")],
            [InlineKeyboardButton(text="🕐 Часовой пояс", callback_data="settings:timezone")],
            [InlineKeyboardButton(text=notif_label, callback_data="settings:toggle:notifications")],
            [InlineKeyboardButton(text=mot_label, callback_data="settings:toggle:motivation")],
            [InlineKeyboardButton(text=ai_label, callback_data="settings:toggle:ai")],
            [InlineKeyboardButton(text="📏 Единицы измерения", callback_data="settings:units")],
            [
                InlineKeyboardButton(
                    text="📋 Изменить профиль",
                    callback_data="settings:profile:edit",
                )
            ],
            [InlineKeyboardButton(text="🔁 Пересчитать КБЖУ", callback_data="settings:recalc")],
            [InlineKeyboardButton(text="🗑 Удалить мои данные", callback_data="settings:data:warn")],
        ],
    )


def timezone_keyboard() -> InlineKeyboardMarkup:
    """Indexed timezone picker (avoids `/` in callback_data)."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=f"settings:tzpick:{idx}",
            ),
        ]
        for idx, (_, label) in enumerate(_TIMEZONES)
    ]
    rows.append(
        [InlineKeyboardButton(text="⬅ Назад", callback_data="settings:main")],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def units_keyboard() -> InlineKeyboardMarkup:
    """Metric vs imperial."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Метрические (кг, см)",
                    callback_data="settings:unit:metric",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Имперские (lb, in)",
                    callback_data="settings:unit:imperial",
                ),
            ],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="settings:main")],
        ],
    )


def delete_confirm_keyboard() -> InlineKeyboardMarkup:
    """Two-step delete confirmation."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить удаление",
                    callback_data="settings:data:confirm",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data="settings:data:cancel",
                ),
            ],
        ],
    )


def back_to_settings_keyboard() -> InlineKeyboardMarkup:
    """Single back action."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅ Назад", callback_data="settings:main")],
        ],
    )


def profile_restart_keyboard() -> InlineKeyboardMarkup:
    """Offer onboarding restart for full profile edits."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Начать перенастройку профиля",
                    callback_data="onboarding:restart",
                ),
            ],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="settings:main")],
        ],
    )


def resolve_timezone(index: int) -> str | None:
    """Map picker index to IANA id."""
    if index < 0 or index >= len(_TIMEZONES):
        return None
    return _TIMEZONES[index][0]
