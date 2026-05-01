from calorie_bot.app.domain import MealDraft


def meal_item_lines(meal: MealDraft) -> list[str]:
    """Return compact text lines for meal draft items."""
    lines: list[str] = []
    for item in meal.items:
        macros: list[str] = []
        if item.protein_g is not None:
            macros.append(f"Б {item.protein_g:.0f} г")
        if item.fat_g is not None:
            macros.append(f"Ж {item.fat_g:.0f} г")
        if item.carbs_g is not None:
            macros.append(f"У {item.carbs_g:.0f} г")
        macro_text = f" ({', '.join(macros)})" if macros else ""
        portion = f", {item.portion_text}" if item.portion_text else ""
        lines.append(f"- {item.name}{portion}: {item.calories} ккал{macro_text}")
    return lines
