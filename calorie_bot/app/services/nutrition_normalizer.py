"""Rounding and plausibility checks for displayed nutrition (no silent auto-fix of AI output)."""

from __future__ import annotations

from calorie_bot.app.utils.calories import calories_from_macros

# Max relative gap between declared line kcal and Atwater(БЖУ) before we align to macros.
_ATWATER_LINE_MISMATCH_REL: float = 0.10


def normalize_calories_kcal(value: float) -> int:
    """Round food energy to whole kcal for UI and storage totals."""
    return max(0, int(round(value)))


def normalize_macro_g(value: float | None) -> float | None:
    """One decimal place for macro grams in user-facing strings."""
    if value is None:
        return None
    return round(float(value), 1)


def implied_energy_from_macros_kcal(
    protein_g: float | None,
    fat_g: float | None,
    carbs_g: float | None,
) -> float:
    """Atwater-style kcal from macros (4 / 9 / 4)."""
    p = protein_g or 0.0
    f = fat_g or 0.0
    c = carbs_g or 0.0
    return p * 4.0 + f * 9.0 + c * 4.0


def macro_energy_matches_calories(
    protein_g: float | None,
    fat_g: float | None,
    carbs_g: float | None,
    calories: float | None,
    *,
    max_relative_error: float = 0.15,
) -> bool:
    """Return True if P/C/F energy is within ``max_relative_error`` of stated calories.

    If calories or all macros are missing/zero, no check — returns True.
    Per product spec: if mismatch > 15%, do **not** auto-recalculate; leave values as-is.
    """
    if calories is None or calories <= 0:
        return True
    implied = implied_energy_from_macros_kcal(protein_g, fat_g, carbs_g)
    if implied <= 0:
        return True
    return abs(implied - float(calories)) / float(calories) <= max_relative_error


def atwater_calories_from_line_macros(
    protein_g: float | None,
    fat_g: float | None,
    carbs_g: float | None,
) -> int | None:
    """Return rounded Atwater kcal when all three macros are known; otherwise ``None``."""
    if protein_g is None or fat_g is None or carbs_g is None:
        return None
    return calories_from_macros(float(protein_g), float(fat_g), float(carbs_g))


def should_align_line_calories_with_macros(
    protein_g: float | None,
    fat_g: float | None,
    carbs_g: float | None,
    calories: int | None,
) -> bool:
    """True if full macros and declared kcal diverge beyond :data:`_ATWATER_LINE_MISMATCH_REL`."""
    atw = atwater_calories_from_line_macros(protein_g, fat_g, carbs_g)
    if atw is None or atw <= 0:
        return False
    if calories is None:
        return True
    return not macro_energy_matches_calories(
        protein_g,
        fat_g,
        carbs_g,
        float(calories),
        max_relative_error=_ATWATER_LINE_MISMATCH_REL,
    )
