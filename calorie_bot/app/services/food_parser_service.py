"""Extract user-stated grams from free text and enforce priority over AI estimates."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.domain import GramsSource
from calorie_bot.app.services import quantity_resolver
from calorie_bot.app.services.quantity_phrase_parser import (
    ParsedQuantityPhrase,
    canonical_food_key,
    parse_quantity_phrase,
)

if TYPE_CHECKING:
    from calorie_bot.app.services.calorie_service import CalorieService

# Explicit mass grams in user text (not ккал). Supports "50 г", "50г", "150 грам", "50 грамм".
_GRAM_PATTERN = re.compile(
    r"(?P<val>\d+(?:[.,]\d+)?)\s*(?:г(?:рамм?(?:ов|а|е)?)?|гр)(?:\b|$)",
    re.IGNORECASE | re.UNICODE,
)

_ORDINAL_PREFIX_PATTERNS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"\bперв(ое|ый|ая|ом|ой)\b", re.IGNORECASE), 0),
    (re.compile(r"\bвтор(ое|ой|ая|ом)\b", re.IGNORECASE), 1),
    (re.compile(r"\bтреть(е|ий|я|им)\b", re.IGNORECASE), 2),
    (re.compile(r"\bчетв[её]рт(ое|ый|ая|ым)\b", re.IGNORECASE), 3),
)


def extract_ordered_gram_values(text: str) -> list[float]:
    """Return gram amounts in left-to-right order from the user's message."""
    out: list[float] = []
    if not text:
        return out
    for match in _GRAM_PATTERN.finditer(text):
        raw = match.group("val").replace(",", ".")
        out.append(float(raw))
    return out


def _gram_matches_with_positions(text: str) -> list[tuple[int, float]]:
    """Pairs (start_index, grams) in text order."""
    matches: list[tuple[int, float]] = []
    for match in _GRAM_PATTERN.finditer(text):
        raw = match.group("val").replace(",", ".")
        matches.append((match.start(), float(raw)))
    return matches


def _ordinal_item_index_from_prefix(prefix: str) -> int | None:
    """Return 0-based item index when Russian ordinal precedes the gram token."""
    for pattern, idx in _ORDINAL_PREFIX_PATTERNS:
        if pattern.search(prefix):
            return idx
    return None


def _best_item_index_for_lone_gram(
    user_text: str,
    items: list[FoodItemRecognition],
    gram_start: int,
) -> int:
    """Pick the food line whose name appears last before the explicit gram token."""
    prefix = user_text[:gram_start]
    lowered_prefix = prefix.lower()
    best_i = 0
    best_pos = -1
    for i, item in enumerate(items):
        name = item.name.strip()
        if not name:
            continue
        pos = -1
        for word in name.lower().split():
            if len(word) < 2:
                continue
            found = lowered_prefix.rfind(word)
            if found > pos:
                pos = found
        full_pos = lowered_prefix.rfind(name.lower())
        if full_pos > pos:
            pos = full_pos
        if pos > best_pos:
            best_pos = pos
            best_i = i
    return best_i


def _base_grams_for_portion_hint(item: FoodItemRecognition) -> float | None:
    if item.estimated_grams is not None:
        return float(item.estimated_grams)
    if item.grams_min is not None and item.grams_max is not None:
        return (float(item.grams_min) + float(item.grams_max)) / 2.0
    return None


def apply_portion_qualifier_text(
    user_text: str | None,
    result: FoodRecognitionResult,
    calorie_service: CalorieService,
) -> FoodRecognitionResult:
    """Scale a single-item draft when the user says small/medium/large/half portion."""
    if not user_text or not user_text.strip() or len(result.items) != 1:
        return result
    if _gram_matches_with_positions(user_text):
        return result
    t = user_text.lower()
    mult: float | None = None
    if "половин" in t:
        mult = 0.5
    elif "маленьк" in t or "маленькая порция" in t:
        mult = 0.65
    elif "больш" in t or "большая порция" in t:
        mult = 1.45
    elif "средн" in t or "средняя порция" in t:
        mult = 1.0
    if mult is None:
        return result
    base = _base_grams_for_portion_hint(result.items[0])
    if base is None or base <= 0:
        return result
    new_g = max(1.0, round(base * mult, 1))
    return calorie_service.update_grams(result, 1, new_g, grams_source=GramsSource.USER.value)


def resolve_quantity_target_index(
    parsed: ParsedQuantityPhrase,
    items: list[FoodItemRecognition],
) -> int | None:
    """Pick the item line that the quantity phrase refers to."""
    if not items:
        return None
    if len(items) == 1:
        return 0
    if not parsed.food_key:
        return None
    best_i: int | None = None
    best = 0
    key = parsed.food_key
    for i, it in enumerate(items):
        if key in it.name.lower():
            score = len(key)
            if score > best:
                best = score
                best_i = i
    return best_i


def apply_user_quantity_from_text(
    user_text: str | None,
    result: FoodRecognitionResult,
    calorie_service: CalorieService,
) -> tuple[FoodRecognitionResult, bool]:
    """Expand «2 яблока»-style input using reference unit weights (after explicit grams are ruled out)."""
    if not user_text or not user_text.strip() or not result.items:
        return result, False
    parsed = parse_quantity_phrase(user_text)
    if parsed is None:
        return result, False
    if extract_ordered_gram_values(user_text) and parsed.per_unit_grams is None:
        return result, False
    idx = resolve_quantity_target_index(parsed, result.items)
    if idx is None:
        return result, False
    food_key = parsed.food_key or canonical_food_key(result.items[idx].name)
    if food_key is None:
        return result, False
    try:
        total_g, uw = quantity_resolver.resolve_total_grams(
            quantity=parsed.quantity,
            unit_type=parsed.unit_type,
            food_key=food_key,
            size_modifier=parsed.size_modifier,
            per_unit_grams=parsed.per_unit_grams,
        )
    except ValueError:
        return result, False
    out = calorie_service.apply_quantity_to_item(
        result,
        idx + 1,
        quantity=parsed.quantity,
        unit_type=parsed.unit_type,
        unit_weight_grams=uw,
        total_grams=total_g,
        size_modifier=parsed.size_modifier,
    )
    return out, True


def apply_user_gram_priority(
    user_text: str | None,
    result: FoodRecognitionResult,
    calorie_service: CalorieService,
    *,
    grams_source: str | None = None,
) -> FoodRecognitionResult:
    """Re-scale items when the user gave explicit grams; user mass overrides AI portions."""
    if not user_text or not user_text.strip():
        return result

    gram_values = extract_ordered_gram_values(user_text)
    has_grams = bool(gram_values)
    parsed_qty = parse_quantity_phrase(user_text)
    try_qty_first = (not has_grams) or (
        parsed_qty is not None and parsed_qty.per_unit_grams is not None
    )
    out = result
    qty_applied = False
    if try_qty_first:
        out, qty_applied = apply_user_quantity_from_text(user_text, out, calorie_service)

    if not has_grams and not qty_applied:
        out = apply_portion_qualifier_text(user_text, out, calorie_service)

    if qty_applied:
        return out

    src = grams_source or GramsSource.USER.value

    matches = _gram_matches_with_positions(user_text)
    if not matches:
        return out

    values = [g for _, g in matches]
    positions = [p for p, _ in matches]
    n_items = len(out.items)
    n_grams = len(values)
    if n_items == 0:
        return out

    if n_items == 1:
        target = values[-1]
        cur = out.items[0].estimated_grams
        if cur is None or abs(float(cur) - target) > 1e-6:
            out = calorie_service.update_grams(out, 1, target, grams_source=src)
        return out

    if n_items == n_grams:
        for idx, grams in enumerate(values):
            cur = out.items[idx].estimated_grams
            if cur is None or abs(float(cur) - grams) > 1e-6:
                out = calorie_service.update_grams(out, idx + 1, grams, grams_source=src)
        return out

    if n_grams == 1 and n_items > 1:
        g = values[0]
        pos = positions[0]
        prefix = user_text[:pos]
        ord_i = _ordinal_item_index_from_prefix(prefix)
        if ord_i is not None and 0 <= ord_i < n_items:
            item_idx = ord_i + 1
        else:
            item_idx = _best_item_index_for_lone_gram(user_text, out.items, pos) + 1
        cur = out.items[item_idx - 1].estimated_grams
        if cur is None or abs(float(cur) - g) > 1e-6:
            out = calorie_service.update_grams(out, item_idx, g, grams_source=src)
        return out

    return out


def try_simple_gram_meal_text(text: str) -> FoodRecognitionResult | None:
    """Parse a single explicit-grams Russian line without LLM (fallback when API/JSON fails).

    Handles patterns such as «гречка 200г», «170 грам шарлотки» (after :data:`_GRAM_PATTERN` fix).
    Returns ``None`` if the message is not exactly one mass + one food name chunk.
    """
    from calorie_bot.app.services.calorie_service import normalize_food_name

    t = (text or "").strip()
    if not t or len(t) > 800:
        return None
    matches = list(_GRAM_PATTERN.finditer(t))
    if len(matches) != 1:
        return None
    m = matches[0]
    raw_val = m.group("val").replace(",", ".")
    try:
        grams = float(raw_val)
    except ValueError:
        return None
    if grams <= 0 or grams > 99_999:
        return None
    name = (t[: m.start()] + " " + t[m.end() :]).strip()
    name = re.sub(r"\s+", " ", name).strip(" ,.;—–-")
    if len(name) < 2:
        return None
    name = normalize_food_name(name)
    if not name or len(name) < 2:
        return None
    item = FoodItemRecognition(
        name=name,
        portion_description=f"{grams:.0f} г",
        estimated_grams=grams,
        calories=None,
        calories_per_100g=None,
        protein=None,
        fat=None,
        carbs=None,
        food_confidence=0.55,
        portion_confidence=0.93,
        grams_source=GramsSource.USER.value,
        needs_portion_clarification=False,
        is_estimated=True,
        confidence=0.55,
    )
    return FoodRecognitionResult(
        items=[item],
        total_calories=0,
        overall_confidence=0.55,
        comment="Запись по явным граммам из сообщения (резерв без LLM).",
        needs_clarification=False,
    )
