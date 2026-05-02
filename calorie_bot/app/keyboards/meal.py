from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def meal_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Return meal draft confirmation keyboard (legacy path; aligns with photo review)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сохранить", callback_data="meal:confirm"),
                InlineKeyboardButton(text="❌ Отменить", callback_data="meal:cancel"),
            ],
            [InlineKeyboardButton(text="✏️ Изменить", callback_data="meal:edit")],
        ]
    )


def photo_review_keyboard() -> InlineKeyboardMarkup:
    """После распознавания — минимум кнопок (сохранить / изменить / добавить / удалить / отмена)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сохранить", callback_data="photo_meal:confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="photo_meal:cancel"),
            ],
            [InlineKeyboardButton(text="✏️ Изменить", callback_data="photo_meal:edit:flex")],
            [
                InlineKeyboardButton(text="➕ Добавить", callback_data="photo_meal:quick:add"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data="photo_meal:quick:delete"),
            ],
        ]
    )


def today_meals_keyboard(meal_ids: list[int]) -> InlineKeyboardMarkup:
    """Return edit/delete controls for today's saved meals."""
    rows = []
    for meal_id in meal_ids:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ Изменить #{meal_id}",
                    callback_data=f"today:edit:{meal_id}",
                ),
                InlineKeyboardButton(
                    text=f"🗑 Удалить #{meal_id}",
                    callback_data=f"today:delete:{meal_id}",
                ),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def meal_type_keyboard(prefix: str = "food") -> InlineKeyboardMarkup:
    """Return keyboard for changing meal type."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Завтрак", callback_data=f"{prefix}:meal_type:breakfast"),
                InlineKeyboardButton(text="Обед", callback_data=f"{prefix}:meal_type:lunch"),
            ],
            [
                InlineKeyboardButton(text="Ужин", callback_data=f"{prefix}:meal_type:dinner"),
                InlineKeyboardButton(text="Перекус", callback_data=f"{prefix}:meal_type:snack"),
            ],
        ]
    )
