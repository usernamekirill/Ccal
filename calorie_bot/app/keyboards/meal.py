"""Meal-related inline keyboards (confirm, type, portion quick-picks)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.utils.food_emoji import food_line_emoji

# Shown after tapping custom row.
PORTION_QUICK_PICK_CUSTOM_LABEL = "✍️ Свой вариант"
PORTION_CUSTOM_FREE_TEXT_HINT = (
    "Напишите изменения одной фразой.\n"
    "Например:\n"
    "• творог 180 г\n"
    "• мёд 20 г\n"
    "• творог 180 г, мёд 20 г\n"
    "• творог 150 г и мёд 30 г"
)

CLARIFY_WEIGHT_PREFIX = "clarify_weight"


def _display_product(product_name: str) -> str:
    """Capitalize Russian line for a button."""
    s = (product_name or "").strip()
    if not s:
        return "Порция"
    return s[0].upper() + s[1:]


def format_multi_item_portion_button_label(product_name: str, grams: int) -> str:
    """Composite dish ingredient preset: «🥣 Творог 150 г» (no shared «… творога и мёда» line)."""
    display = _display_product(product_name)
    emoji = food_line_emoji(display)
    w = f"{int(grams)} г"
    return f"{emoji} {display} {w}"


def format_single_item_portion_button_label(grams: int) -> str:
    """One-product draft: short Telegram button."""
    return f"{int(grams)} г"


def format_item_portion_button_label(product_name: str, grams: int) -> str:
    """Alias for multi-ingredient format (backward compat for tests / call sites)."""
    return format_multi_item_portion_button_label(product_name, grams)


@dataclass(frozen=True)
class PortionQuickPickParsed:
    """Parsed gram quick-pick (``mpt:`` / ``clarify_weight:``)."""

    kind: Literal["custom", "legacy", "indexed"]
    item_index: int | None = None
    grams: int | None = None


def parse_quick_pick_grams_raw(raw: str) -> PortionQuickPickParsed:
    """Parse payload after ``mpt:`` or ``clarify_weight:`` (supports ``item_index=0:weight=150``)."""
    if raw == "x":
        return PortionQuickPickParsed("custom")
    if "item_index=" in raw and "weight=" in raw:
        try:
            left, right = raw.split(":", 1)
            idx = int(left.split("=", 1)[1].strip())
            w = int(right.split("=", 1)[1].strip())
            return PortionQuickPickParsed("indexed", idx, w)
        except (ValueError, IndexError) as e:
            raise ValueError(f"invalid_verbose_clarify_weight:{raw!r}") from e
    parts = raw.split(":")
    if len(parts) == 2 and parts[0].lstrip("-").isdigit() and parts[1].isdigit():
        return PortionQuickPickParsed("indexed", int(parts[0]), int(parts[1]))
    if len(parts) == 1 and parts[0].isdigit():
        return PortionQuickPickParsed("legacy", None, int(parts[0]))
    raise ValueError(f"invalid_grams_quick_pick_payload:{raw!r}")


def parse_portion_quick_pick_payload(raw: str) -> PortionQuickPickParsed:
    """Parse body after the ``mpt:`` prefix."""
    return parse_quick_pick_grams_raw(raw)


def parse_clarify_weight_payload(raw: str) -> PortionQuickPickParsed:
    """Parse body after the ``clarify_weight:`` prefix."""
    return parse_quick_pick_grams_raw(raw)


def portion_pick_synthetic_user_text(fr: FoodRecognitionResult, parsed: PortionQuickPickParsed) -> str:
    """Turn a quick-pick into text for ``FoodTextParserService`` (merge-friendly)."""
    if parsed.kind == "custom" or parsed.grams is None:
        raise ValueError("portion_pick_synthetic_needs_grams")
    grams = int(parsed.grams)
    if parsed.kind == "indexed" and parsed.item_index is not None:
        if not 0 <= parsed.item_index < len(fr.items):
            raise ValueError("portion_pick_bad_item_index")
        name = (fr.items[parsed.item_index].name or "").strip()
        if not name:
            return f"{grams} г"
        return f"{name} {grams} г"
    if len(fr.items) == 1:
        name = (fr.items[0].name or "").strip()
        if name:
            return f"{name} {grams} г"
    return f"{grams} г"


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


def contextual_portion_keyboard(
    actions: list[tuple[int | None, int, str]],
    *,
    single_ingredient_clarification: bool = False,
) -> InlineKeyboardMarkup:
    """Gram quick-picks for clarification (``clarify_weight:``) or legacy ``mpt:``."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for item_index, grams, product_name in actions[:12]:
        g = int(grams)
        if single_ingredient_clarification:
            text = format_single_item_portion_button_label(g)
            cb = f"mpt:{g}"
        else:
            text = format_multi_item_portion_button_label(product_name, g)
            cb = f"{CLARIFY_WEIGHT_PREFIX}:{int(item_index if item_index is not None else 0)}:{g}"
        row.append(InlineKeyboardButton(text=text, callback_data=cb))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    custom_cb = "mpt:x" if single_ingredient_clarification else f"{CLARIFY_WEIGHT_PREFIX}:x"
    rows.append([InlineKeyboardButton(text=PORTION_QUICK_PICK_CUSTOM_LABEL, callback_data=custom_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def portion_quick_pick_keyboard() -> InlineKeyboardMarkup:
    """Quick portion presets when product is unknown (legacy; ``mpt:`` only)."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for g in (100, 150, 200):
        row.append(
            InlineKeyboardButton(
                text=format_single_item_portion_button_label(g),
                callback_data=f"mpt:{g}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text=PORTION_QUICK_PICK_CUSTOM_LABEL, callback_data="mpt:x")])
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
