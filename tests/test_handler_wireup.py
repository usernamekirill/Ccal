"""Smoke checks so handler modules stay importable and wired (regression: dropped imports)."""


def test_text_food_handler_exports_infer_meal_type() -> None:
    """``infer_meal_type`` is used before the main try/except; a missing import breaks all text meals."""
    from calorie_bot.app.handlers import text_food

    assert callable(getattr(text_food, "infer_meal_type", None))
