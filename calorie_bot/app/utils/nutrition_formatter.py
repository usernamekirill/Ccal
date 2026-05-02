"""Telegram copy for one food line: exact / estimate / range / unknown (honest precision)."""

from __future__ import annotations

from calorie_bot.app.ai.schemas import FoodItemRecognition
from calorie_bot.app.services.nutrition_calculator import has_quantified_portion_mass

_ITEM_EMOJI: tuple[tuple[str, str], ...] = (
    ("яблоко", "🍎"),
    ("банан", "🍌"),
    ("апельсин", "🍊"),
    ("груша", "🍐"),
    ("хлеб", "🍞"),
    ("яйцо", "🥚"),
)


def _item_emoji(name: str) -> str:
    low = name.lower()
    for key, emoji in _ITEM_EMOJI:
        if key in low:
            return emoji
    return "🍽"


def _title_case_ru(name: str) -> str:
    if not name:
        return name
    return name[0].upper() + name[1:]


def _format_qty_display(quantity: float) -> str:
    if abs(quantity - round(quantity)) < 1e-9:
        return str(int(round(quantity)))
    return str(quantity).replace(".", ",")


def _portion_is_exact_user(item: FoodItemRecognition) -> bool:
    return item.estimated_grams is not None and item.grams_source in (
        "user",
        "user_quantity",
        "text_correction",
        "voice_correction",
    )


def _portion_is_exact_confident_ai(item: FoodItemRecognition) -> bool:
    """AI point mass treated as «точный» UX only when model claims non-estimated + confident portion."""
    return (
        item.estimated_grams is not None
        and not item.is_estimated
        and item.portion_confidence >= 0.75
        and item.grams_min is None
    )


def _show_item_macros(item: FoodItemRecognition) -> bool:
    """БЖУ только при понятной порции и достаточной уверенности — без «псевдоточности»."""
    if not has_quantified_portion_mass(item.estimated_grams, item.grams_min, item.grams_max):
        return False
    if _portion_is_exact_user(item) or _portion_is_exact_confident_ai(item):
        return True
    if item.grams_min is not None and item.grams_max is not None:
        return item.portion_confidence >= 0.6
    if item.estimated_grams is not None:
        if not item.is_estimated and item.portion_confidence >= 0.6:
            return True
        if item.is_estimated and item.portion_confidence >= 0.75:
            return True
    return False


def format_item_block(item: FoodItemRecognition) -> list[str]:
    """Build human-readable lines for a single recognized item (emoji + mass + kcal + macros)."""
    emoji = _item_emoji(item.name)
    title = _title_case_ru(item.name)
    lines: list[str] = []

    used_quantity_line = False
    if (
        item.quantity is not None
        and item.grams_source == "user_quantity"
        and item.estimated_grams is not None
        and item.unit_type
    ):
        qd = _format_qty_display(item.quantity)
        g = item.estimated_grams
        if item.unit_type == "piece":
            lines.append(f"{emoji} {title} — {qd} шт (~{g:.0f} г)")
            used_quantity_line = True
        elif item.unit_type == "slice":
            lines.append(f"{emoji} {title} — {qd} ломт. (~{g:.0f} г)")
            used_quantity_line = True
        elif item.unit_type == "portion":
            lines.append(f"{emoji} {title} — {qd} порц. (~{g:.0f} г)")
            used_quantity_line = True

    if not used_quantity_line and item.estimated_grams is not None:
        if _portion_is_exact_user(item) or _portion_is_exact_confident_ai(item):
            lines.append(f"{emoji} {title} — {item.estimated_grams:.0f} г")
        else:
            lines.append(f"{emoji} {title} — ~{item.estimated_grams:.0f} г")
    elif not used_quantity_line and item.grams_min is not None and item.grams_max is not None:
        lines.append(f"{emoji} {title} — {item.grams_min:.0f}–{item.grams_max:.0f} г")
    elif not used_quantity_line:
        lines.append(f"{emoji} {title}")
        lines.append("Порция неясна")
        lines.append("👉 Напишите вес, например: «50 г»")
        return lines

    if item.calories is not None:
        if _portion_is_exact_user(item) or _portion_is_exact_confident_ai(item):
            lines.append(f"{item.calories} ккал")
        else:
            lines.append(f"≈ {item.calories} ккал")
    elif item.calories_min is not None and item.calories_max is not None:
        lines.append(f"≈ {item.calories_min}–{item.calories_max} ккал")

    if _show_item_macros(item):
        if item.protein is not None or item.fat is not None or item.carbs is not None:
            parts: list[str] = []
            if item.protein is not None:
                parts.append(f"Б {item.protein:g}")
            if item.fat is not None:
                parts.append(f"Ж {item.fat:g}")
            if item.carbs is not None:
                parts.append(f"У {item.carbs:g}")
            if parts:
                lines.append(" · ".join(parts))
        elif item.protein_min is not None and item.protein_max is not None:
            lines.append(
                f"Б {item.protein_min:g}–{item.protein_max:g} · "
                f"Ж {item.fat_min or 0:g}–{item.fat_max or 0:g} · "
                f"У {item.carbs_min or 0:g}–{item.carbs_max or 0:g}"
            )

    return lines


def meal_has_unknown_portion_items(items: list[FoodItemRecognition]) -> bool:
    """Any line without quantified mass (no honest kcal)."""
    return not all(
        has_quantified_portion_mass(i.estimated_grams, i.grams_min, i.grams_max) for i in items
    )
