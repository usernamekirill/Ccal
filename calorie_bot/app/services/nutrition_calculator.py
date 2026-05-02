"""Pure nutrition math: kcal and macros from per-100g values and mass (point or range).

Used by CalorieService and tests. Does not apply user-priority rules — only arithmetic.
"""

from __future__ import annotations


def calories_from_per_100g(kcal_per_100g: float, grams: float) -> int:
    """Total kilocalories for ``grams`` at ``kcal_per_100g`` density."""
    return round(kcal_per_100g * grams / 100.0)


def macro_g_from_per_100g(g_per_100g: float | None, grams: float) -> float | None:
    """Grams of a macro for ``grams`` of food; ``None`` if density unknown."""
    if g_per_100g is None:
        return None
    return round(g_per_100g * grams / 100.0, 1)


def calorie_range_from_per_100g(kcal_per_100g: float, grams_min: float, grams_max: float) -> tuple[int, int]:
    """Inclusive-ish kcal band when only a mass range is known."""
    lo = round(kcal_per_100g * grams_min / 100.0)
    hi = round(kcal_per_100g * grams_max / 100.0)
    return (min(lo, hi), max(lo, hi))


def macro_range_from_per_100g(
    g_per_100g: float | None,
    grams_min: float,
    grams_max: float,
) -> tuple[float | None, float | None]:
    """Macro grams band; (None, None) if density unknown."""
    if g_per_100g is None:
        return (None, None)
    a = round(g_per_100g * grams_min / 100.0, 1)
    b = round(g_per_100g * grams_max / 100.0, 1)
    return (min(a, b), max(a, b))
