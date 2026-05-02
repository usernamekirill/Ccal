"""Rounding and plausibility checks for displayed nutrition (no silent auto-fix of AI output)."""

from __future__ import annotations


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
