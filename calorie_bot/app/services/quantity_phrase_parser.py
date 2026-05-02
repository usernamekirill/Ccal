"""Rule-based parsing of Russian quantity phrases (штуки, ломтики, половина, размер)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from calorie_bot.app.domain import PortionSizeModifier, PortionUnitType
from calorie_bot.app.services.unit_weight_service import list_known_food_keys

_WORD_NUMBERS: dict[str, float] = {
    "один": 1,
    "одна": 1,
    "одно": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
}

_EDIT_VERB_PREFIX = re.compile(
    r"^(?:это|сделай|сделайте|там|ну|пусть|замени|поменяй)\s+",
    re.IGNORECASE | re.UNICODE,
)

_SIZE_TOKEN = re.compile(
    r"^(маленьк\w*|больш\w*|средн\w*)\s+",
    re.IGNORECASE | re.UNICODE,
)

# Яблоко / яйцо / ломтик… → canonical food key
_FOOD_FROM_FRAGMENT: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:кусоч\w*|ломт(ик|ца|ков)?)\s+(?:хлеба|хлеб)\b"), "хлеб"),
    (re.compile(r"\bхлеба?\b"), "хлеб"),
    (re.compile(r"\bяблок\w*\b"), "яблоко"),
    (re.compile(r"\bбанан\w*\b"), "банан"),
    (re.compile(r"\bяйц\w*\b"), "яйцо"),
    (re.compile(r"\bапельсин\w*\b"), "апельсин"),
    (re.compile(r"\bгруш\w*\b"), "груша"),
]

_SLICE_WORD = re.compile(
    r"\b(?:кусоч\w*|ломт(ик|ика|иков|ика хлеба)?)\b",
    re.IGNORECASE | re.UNICODE,
)


def _strip_size_prefix(fragment: str) -> tuple[str | None, str]:
    """Return ``(size_modifier | None, rest)`` if a size adjective leads the fragment."""
    m = _SIZE_TOKEN.match(fragment.strip())
    if not m:
        return None, fragment.strip()
    raw = m.group(1).lower()
    rest = fragment[m.end() :].strip()
    if raw.startswith("маленьк"):
        return PortionSizeModifier.SMALL.value, rest
    if raw.startswith("больш"):
        return PortionSizeModifier.LARGE.value, rest
    if raw.startswith("средн"):
        return PortionSizeModifier.MEDIUM.value, rest
    return None, fragment.strip()


def canonical_food_key(fragment: str) -> str | None:
    """Map a free fragment to a key present in the unit-weight table."""
    low = fragment.lower().strip()
    if not low:
        return None
    for pattern, key in _FOOD_FROM_FRAGMENT:
        if pattern.search(low):
            if key in list_known_food_keys():
                return key
    known = list_known_food_keys()
    for k in sorted(known, key=len, reverse=True):
        if k in low:
            return k
    return None


def _detect_unit_type(food_tail: str) -> tuple[str, str]:
    """Return ``(unit_type, cleaned_tail)``."""
    t = food_tail.lower()
    if _SLICE_WORD.search(t) or re.search(r"\bхлеб\w*\b", t):
        if _SLICE_WORD.search(t):
            cleaned = _SLICE_WORD.sub("", food_tail).strip()
            cleaned = re.sub(r"\bхлеба?\b", "", cleaned, flags=re.I).strip()
            return PortionUnitType.SLICE.value, cleaned or "хлеб"
        if re.search(r"\b(?:кусоч|ломт)\w*\b", t):
            return PortionUnitType.SLICE.value, "хлеб"
    if re.search(r"\bпорци\w*\b", t):
        return PortionUnitType.PORTION.value, food_tail
    return PortionUnitType.PIECE.value, food_tail


def _parse_leading_number(fragment: str) -> tuple[float | None, str]:
    """Parse ``(quantity, rest)`` for a leading digit or Russian number word."""
    frag = fragment.strip()
    m = re.match(r"^(\d+[\.,]?\d*)\s+", frag)
    if m:
        qty = float(m.group(1).replace(",", "."))
        return qty, frag[m.end() :].strip()

    m2 = re.match(
        r"^(один|одна|одно|два|две|три|четыре|пять|шесть|семь|восемь|девять|десять)\s+",
        frag,
        re.I,
    )
    if m2:
        w = m2.group(1).lower()
        return _WORD_NUMBERS.get(w, None), frag[m2.end() :].strip()
    return None, frag


@dataclass(frozen=True)
class ParsedQuantityPhrase:
    """Structured count/size product phrase (pre–nutrition layer)."""

    food_key: str | None
    quantity: float
    unit_type: str
    size_modifier: str | None


def parse_quantity_phrase(user_text: str) -> ParsedQuantityPhrase | None:
    """Parse ``user_text`` into quantity metadata, or ``None`` if not applicable."""
    if not user_text or not user_text.strip():
        return None

    text = _EDIT_VERB_PREFIX.sub("", user_text.strip())
    text = re.sub(r"^[,:;\s]+", "", text).strip()
    if not text:
        return None

    lower = text.lower()
    quantity: float | None = None
    size_modifier: str | None = None
    rest = text

    if re.match(r"^(?:половина|пол)\s+", lower):
        quantity = 0.5
        rest = re.sub(r"^(?:половина|пол)\s+", "", text, count=1, flags=re.I).strip()
        ut, tail = _detect_unit_type(rest)
        key = canonical_food_key(tail if tail else rest)
        if key is None:
            return None
        return ParsedQuantityPhrase(
            food_key=key,
            quantity=quantity,
            unit_type=ut,
            size_modifier=size_modifier,
        )

    m_pieces = re.match(r"^(\d+[\.,]?\d*)\s+штук\w*\b", lower)
    if m_pieces:
        quantity = float(m_pieces.group(1).replace(",", "."))
        return ParsedQuantityPhrase(
            food_key=None,
            quantity=quantity,
            unit_type=PortionUnitType.PIECE.value,
            size_modifier=None,
        )

    # Size-leading, implicit qty 1: «большое яблоко»
    sz0, after_size = _strip_size_prefix(rest)
    if sz0 and after_size:
        q2, after_num = _parse_leading_number(after_size)
        if q2 is None:
            ut, tail = _detect_unit_type(after_size)
            key = canonical_food_key(tail if tail else after_size)
            if key is None:
                return None
            return ParsedQuantityPhrase(
                food_key=key,
                quantity=1.0,
                unit_type=ut,
                size_modifier=sz0,
            )
        rest = after_size

    quantity, after_num = _parse_leading_number(rest)
    if quantity is None:
        return None

    # «2 больших яблока» / «2 маленьких яблока»
    inner_size, tail = _strip_size_prefix(after_num)
    if inner_size:
        size_modifier = inner_size
    else:
        tail = after_num

    ut, name_fragment = _detect_unit_type(tail)
    key = canonical_food_key(name_fragment if name_fragment else tail)
    if key is None:
        return None

    return ParsedQuantityPhrase(
        food_key=key,
        quantity=quantity,
        unit_type=ut,
        size_modifier=size_modifier,
    )
