"""Resolve total grams from quantity, unit reference weight, and optional size."""

from __future__ import annotations

from calorie_bot.app.services import unit_weight_service


def resolve_total_grams(
    *,
    quantity: float,
    unit_type: str,
    food_key: str,
    size_modifier: str | None,
    per_unit_grams: float | None = None,
) -> tuple[float, float]:
    """Return ``(total_grams, unit_weight_grams)`` from reference data.

    When ``per_unit_grams`` is set (e.g. «2 блина по 70 г»), it overrides the table
    and becomes both the per-unit mass and the divisor basis for ``quantity``.
    """
    if per_unit_grams is not None and float(per_unit_grams) > 0:
        uw = float(per_unit_grams)
        total = max(0.1, round(float(quantity) * uw, 1))
        return total, uw

    uw = unit_weight_service.get_reference_unit_weight_grams(food_key, unit_type, size_modifier)
    if uw is None or uw <= 0:
        raise ValueError("unknown_unit_weight")
    total = max(0.1, round(float(quantity) * float(uw), 1))
    return total, uw
