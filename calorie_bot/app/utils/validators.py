def parse_positive_float(value: str | None) -> float | None:
    """Parse a positive float from user text."""
    if value is None:
        return None
    try:
        parsed = float(value.strip().replace(",", "."))
    except ValueError:
        return None
    return parsed if parsed > 0 else None
