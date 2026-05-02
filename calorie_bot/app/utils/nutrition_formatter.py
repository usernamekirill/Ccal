"""Telegram copy for one food line: exact / estimate / range / unknown (honest precision)."""

from __future__ import annotations

from calorie_bot.app.ai.schemas import FoodItemRecognition


def _portion_is_exact_user(item: FoodItemRecognition) -> bool:
    return item.estimated_grams is not None and item.grams_source in (
        "user",
        "text_correction",
        "voice_correction",
    )


def _portion_is_exact_confident_ai(item: FoodItemRecognition) -> bool:
    return (
        item.estimated_grams is not None
        and not item.is_estimated
        and item.portion_confidence >= 0.75
        and item.grams_min is None
    )


def format_item_block(item: FoodItemRecognition) -> list[str]:
    """Build human-readable lines for a single recognized item (emoji + mass + kcal + macros)."""
    emoji = "🍽"
    lines: list[str] = []

    if item.estimated_grams is not None:
        if _portion_is_exact_user(item) or _portion_is_exact_confident_ai(item):
            lines.append(f"{emoji} {item.name} — {item.estimated_grams:.0f} г")
        else:
            lines.append(f"{emoji} {item.name} — ~{item.estimated_grams:.0f} г")
    elif item.grams_min is not None and item.grams_max is not None:
        lines.append(f"{emoji} {item.name} — {item.grams_min:.0f}–{item.grams_max:.0f} г")
    else:
        lines.append(f"{emoji} {item.name}")
        lines.append("Порция неясна")
        lines.append('Напишите: «50 г»')
        return lines

    if item.calories is not None:
        if _portion_is_exact_user(item) or _portion_is_exact_confident_ai(item):
            lines.append(f"{item.calories} ккал")
        else:
            lines.append(f"≈ {item.calories} ккал")
    elif item.calories_min is not None and item.calories_max is not None:
        lines.append(f"≈ {item.calories_min}–{item.calories_max} ккал")

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

    if item.grams_min is not None and item.estimated_grams is None:
        lines.append("Порция примерная")

    return lines
