"""Resolve total grams from quantity, unit reference weight, and optional size."""

from __future__ import annotations

from calorie_bot.app.services import unit_weight_service


def resolve_total_grams(
    *,
    quantity: float,
    unit_type: str,
    food_key: str,
    size_modifier: str | None,
) -> tuple[float, float]:
    """Return ``(total_grams, unit_weight_grams)`` from reference data.

    ``food_key`` is a canonical lookup key (e.g. ``«яблоко»``). Raises ``ValueError``
    if the reference table has no entry.
    """
    uw = unit_weight_service.get_reference_unit_weight_grams(food_key, unit_type, size_modifier)
    if uw is None or uw <= 0:
        raise ValueError("unknown_unit_weight")
    total = max(0.1, round(float(quantity) * float(uw), 1))
    return total, uw
