from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def meal_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Return meal draft confirmation keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сохранить", callback_data="meal:confirm"),
                InlineKeyboardButton(text="❌ Отменить", callback_data="meal:cancel"),
            ],
            [InlineKeyboardButton(text="🎙 Сказать голосом", callback_data="meal:voice")],
        ]
    )


def photo_review_keyboard() -> InlineKeyboardMarkup:
    """Return photo recognition review keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сохранить", callback_data="photo_meal:confirm"),
                InlineKeyboardButton(text="❌ Отменить", callback_data="photo_meal:cancel"),
            ],
            [InlineKeyboardButton(text="✏️ Изменить", callback_data="photo_meal:edit:name")],
            [
                InlineKeyboardButton(
                    text="⚖️ Изменить граммовку",
                    callback_data="photo_meal:edit:grams",
                ),
                InlineKeyboardButton(
                    text="🔥 Изменить калории",
                    callback_data="photo_meal:edit:calories",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="➕ Добавить продукт",
                    callback_data="photo_meal:edit:add",
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить продукт",
                    callback_data="photo_meal:edit:delete",
                ),
            ],
            [InlineKeyboardButton(text="🎙 Сказать голосом", callback_data="meal:voice")],
            [InlineKeyboardButton(text="Изменить тип приема", callback_data="food:meal_type")],
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
