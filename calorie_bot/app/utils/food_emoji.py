"""Best-effort food → emoji for Telegram lines (no service dependencies)."""


def food_line_emoji(name: str) -> str:
    """Pick a Telegram-friendly emoji for a food name (best-effort)."""
    n = (name or "").lower()
    if any(k in n for k in ("торт", "кекс", "шарлот", "пирог", "бисквит", "чизкейк")):
        return "🍰"
    if any(k in n for k in ("суп", "борщ", "бульон")):
        return "🍲"
    if any(k in n for k in ("чай", "кофе", "сок", "кола")):
        return "🥤"
    if any(k in n for k in ("хлеб", "булоч", "батон")):
        return "🍞"
    if any(k in n for k in ("греч", "рис", "паста", "макарон", "пюре")):
        return "🍽"
    if any(k in n for k in ("яблок", "банан", "фрукт", "ягод")):
        return "🍎"
    return "🍽"
