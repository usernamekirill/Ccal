"""Compact Telegram copy for meal recognition (preview + saved brief)."""

from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.domain import MealType


def _meal_type_ru(value: str | None) -> str | None:
    if not value:
        return None
    labels = {
        MealType.BREAKFAST.value: "завтрак",
        MealType.LUNCH.value: "обед",
        MealType.DINNER.value: "ужин",
        MealType.SNACK.value: "перекус",
    }
    return labels.get(value)


def format_meal_review(
    result: FoodRecognitionResult,
    *,
    show_low_confidence_hint: bool = False,
) -> str:
    """Short confirmation card: item lines, per-item kcal, total; no comment/disclaimer blocks."""
    blocks: list[str] = []
    for item in result.items:
        line1 = f"🍽 {item.name} — {item.estimated_grams:.0f} г"
        line2 = f"≈ {item.calories} ккал"
        blocks.append("\n".join([line1, line2]))
    body = "\n\n".join(blocks)
    lines = [body, "", f"Итого: {result.total_calories} ккал"]
    mt = _meal_type_ru(result.meal_type)
    if mt:
        lines.append(f"Приём: {mt}")
    if show_low_confidence_hint:
        lines.append("\n⚠️ Оценка примерная — проверь порцию.")
    return "\n".join(lines)


def format_saved_brief(result: FoodRecognitionResult) -> str:
    """Minimal text after saving a meal."""
    if len(result.items) == 1:
        it = result.items[0]
        return f"🍽 {it.name} — {it.estimated_grams:.0f} г\n≈ {it.calories} ккал\n\nИтого: {result.total_calories} ккал"
    lines = []
    for it in result.items:
        lines.append(f"• {it.name} — {it.estimated_grams:.0f} г, {it.calories} ккал")
    lines.append(f"\nИтого: {result.total_calories} ккал")
    return "\n".join(lines)
