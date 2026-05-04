"""Meal recognition card: totals, meal type, hints (item lines from nutrition_formatter)."""

from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.domain import MealType
from calorie_bot.app.utils.calories import calories_from_macros
from calorie_bot.app.utils.nutrition_formatter import format_item_block, meal_has_unknown_portion_items


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


def _mid_item_calories(item) -> int:  # FoodItemRecognition
    if item.calories is not None:
        return item.calories
    if item.calories_min is not None and item.calories_max is not None:
        return (item.calories_min + item.calories_max) // 2
    return 0


def _meal_macro_totals_g(items: list) -> tuple[float, float, float]:
    """Sum point-macro grams across recognition lines (lines without protein count as 0)."""
    p = sum(i.protein or 0 for i in items)
    f = sum(i.fat or 0 for i in items)
    c = sum(i.carbs or 0 for i in items)
    return p, f, c


def format_meal_review(
    result: FoodRecognitionResult,
    *,
    show_low_confidence_hint: bool = False,
) -> str:
    """Confirmation card with honest grams/calories (point, range, or clarify)."""
    blocks = ["\n".join(format_item_block(item)) for item in result.items]
    body = "\n\n".join(blocks)
    lines: list[str] = [body, ""]

    unknown_any = meal_has_unknown_portion_items(result.items)
    if result.total_calories_min is not None and result.total_calories_max is not None:
        lines.append(f"Итого: ≈ {result.total_calories_min}–{result.total_calories_max} ккал")
    elif unknown_any and result.total_calories == 0:
        lines.append("Итого: уточните порции, чтобы посчитать калории")
    else:
        lines.append(f"Итого: ≈ {result.total_calories} ккал")

    if result.items:
        p_tot, f_tot, c_tot = _meal_macro_totals_g(result.items)
        if p_tot > 0 or f_tot > 0 or c_tot > 0:
            lines.append(f"БЖУ всего: Б {p_tot:g} · Ж {f_tot:g} · У {c_tot:g} г")
            atw_total = calories_from_macros(p_tot, f_tot, c_tot)
            if (
                result.total_calories > 0
                and result.total_calories_min is None
                and result.total_calories_max is None
            ):
                rel = abs(atw_total - result.total_calories) / float(result.total_calories)
                if rel > 0.08:
                    lines.append(
                        f"⚠️ Сумма ккал ({result.total_calories}) и ккал из суммарного БЖУ "
                        f"({atw_total}) заметно расходятся (~{rel * 100:.0f}%)."
                    )

    mt = _meal_type_ru(result.meal_type)
    if mt:
        lines.append(f"Приём: {mt}")

    if result.needs_portion_clarification:
        lines.append(
            "\nЯ понял блюдо, но не уверен в размере порции. "
            "Напишите вес, например: 50 г.",
        )

    if show_low_confidence_hint:
        lines.append("\n⚠️ Оценка примерная — проверь порцию и размер.")

    return "\n".join(lines)


def format_saved_brief(result: FoodRecognitionResult) -> str:
    """Minimal text after saving a meal."""
    if len(result.items) == 1:
        it = result.items[0]
        block = "\n".join(format_item_block(it))
        if result.total_calories_min is not None and result.total_calories_max is not None:
            total = f"Итого: ≈ {result.total_calories_min}–{result.total_calories_max} ккал"
        elif meal_has_unknown_portion_items(result.items) and result.total_calories == 0:
            total = "Итого: без точной порции калории не считаем"
        else:
            total = f"Итого: ≈ {result.total_calories} ккал"
        return f"{block}\n\n{total}"

    lines: list[str] = []
    for it in result.items:
        g = it.estimated_grams
        if g is not None and it.calories is not None:
            lines.append(f"• {it.name} — {g:.0f} г, {it.calories} ккал")
        elif it.grams_min is not None and it.grams_max is not None:
            mid = _mid_item_calories(it)
            lines.append(f"• {it.name} — ~{it.grams_min:.0f}–{it.grams_max:.0f} г, ~{mid} ккал")
        else:
            lines.append(f"• {it.name} — порция уточняется")
    if result.total_calories_min is not None and result.total_calories_max is not None:
        lines.append(f"\nИтого: ≈ {result.total_calories_min}–{result.total_calories_max} ккал")
    elif meal_has_unknown_portion_items(result.items) and result.total_calories == 0:
        lines.append("\nИтого: уточните порции для точной суммы")
    else:
        lines.append(f"\nИтого: ≈ {result.total_calories} ккал")
    return "\n".join(lines)
