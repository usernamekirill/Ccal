"""Reference average mass per countable unit (RU foods) for quantity→grams resolution."""

from __future__ import annotations

from calorie_bot.app.domain import PortionSizeModifier, PortionUnitType

# (food_key, unit_type) → {size_or_role → grams per single unit}
_REFERENCE_GRAMS: dict[tuple[str, str], dict[str, float]] = {
    ("яблоко", PortionUnitType.PIECE.value): {
        PortionSizeModifier.SMALL.value: 100.0,
        PortionSizeModifier.MEDIUM.value: 136.0,
        PortionSizeModifier.LARGE.value: 180.0,
    },
    ("банан", PortionUnitType.PIECE.value): {
        PortionSizeModifier.SMALL.value: 90.0,
        PortionSizeModifier.MEDIUM.value: 118.0,
        PortionSizeModifier.LARGE.value: 150.0,
    },
    ("яйцо", PortionUnitType.PIECE.value): {
        PortionSizeModifier.SMALL.value: 45.0,
        PortionSizeModifier.MEDIUM.value: 50.0,
        PortionSizeModifier.LARGE.value: 60.0,
    },
    ("хлеб", PortionUnitType.SLICE.value): {
        "slice": 30.0,
        PortionSizeModifier.SMALL.value: 25.0,
        PortionSizeModifier.MEDIUM.value: 30.0,
        PortionSizeModifier.LARGE.value: 40.0,
    },
    ("апельсин", PortionUnitType.PIECE.value): {
        PortionSizeModifier.SMALL.value: 100.0,
        PortionSizeModifier.MEDIUM.value: 130.0,
        PortionSizeModifier.LARGE.value: 160.0,
    },
    ("груша", PortionUnitType.PIECE.value): {
        PortionSizeModifier.SMALL.value: 140.0,
        PortionSizeModifier.MEDIUM.value: 170.0,
        PortionSizeModifier.LARGE.value: 220.0,
    },
    ("блин", PortionUnitType.PIECE.value): {
        PortionSizeModifier.SMALL.value: 45.0,
        PortionSizeModifier.MEDIUM.value: 55.0,
        PortionSizeModifier.LARGE.value: 70.0,
    },
    ("сырник", PortionUnitType.PIECE.value): {
        PortionSizeModifier.SMALL.value: 55.0,
        PortionSizeModifier.MEDIUM.value: 70.0,
        PortionSizeModifier.LARGE.value: 90.0,
    },
}


def get_reference_unit_weight_grams(
    food_key: str,
    unit_type: str,
    size_modifier: str | None,
) -> float | None:
    """Return average grams for one unit of ``food_key`` or ``None`` if unknown.

    ``food_key`` must be a canonical key (e.g. ``«яблоко»``). ``unit_type`` follows
    :class:`PortionUnitType`. For slices of bread, ``size_modifier`` selects slice
    thickness when no dedicated slice row exists.
    """
    key = (food_key, unit_type)
    row = _REFERENCE_GRAMS.get(key)
    if row is None:
        return None

    if unit_type == PortionUnitType.SLICE.value and food_key == "хлеб":
        if size_modifier == PortionSizeModifier.SMALL.value:
            return row.get(PortionSizeModifier.SMALL.value) or row.get("slice", 30.0)
        if size_modifier == PortionSizeModifier.LARGE.value:
            return row.get(PortionSizeModifier.LARGE.value) or row.get("slice", 30.0)
        return row.get("slice") or row.get(PortionSizeModifier.MEDIUM.value) or 30.0

    size = size_modifier or PortionSizeModifier.MEDIUM.value
    return row.get(size) or row.get(PortionSizeModifier.MEDIUM.value)


def list_known_food_keys() -> frozenset[str]:
    """Food keys that have reference unit weights (for parser matching)."""
    return frozenset(k for k, _ in _REFERENCE_GRAMS.keys())
