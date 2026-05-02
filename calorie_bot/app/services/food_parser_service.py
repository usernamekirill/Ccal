"""Extract user-stated grams from free text and enforce priority over AI estimates."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult

if TYPE_CHECKING:
    from calorie_bot.app.services.calorie_service import CalorieService

# Explicit mass grams in user text (not ккал). Supports "50 г", "50г", "50 грамм".
_GRAM_PATTERN = re.compile(
    r"(?P<val>\d+(?:[.,]\d+)?)\s*(?:г(?:рамм(?:ов|а|е)?)?|гр)(?:\b|$)",
    re.IGNORECASE | re.UNICODE,
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


def apply_user_gram_priority(
    user_text: str | None,
    result: FoodRecognitionResult,
    calorie_service: CalorieService,
) -> FoodRecognitionResult:
    """Re-scale items when the user gave explicit grams; user mass overrides AI portions.

    Priority: explicit ``X г`` in the user's message wins over model ``estimated_grams``.
    Does not convert back to "pieces"; only linear rescale from the previous estimate.
    """
    if not user_text or not user_text.strip():
        return result

    matches = _gram_matches_with_positions(user_text)
    if not matches:
        return result

    values = [g for _, g in matches]
    positions = [p for p, _ in matches]
    n_items = len(result.items)
    n_grams = len(values)
    if n_items == 0:
        return result

    out = result.model_copy(deep=True)

    if n_items == 1:
        target = values[-1]
        if abs(out.items[0].estimated_grams - target) > 1e-6:
            out = calorie_service.update_grams(out, 1, target)
        return out

    if n_items == n_grams:
        for idx, grams in enumerate(values):
            if abs(out.items[idx].estimated_grams - grams) > 1e-6:
                out = calorie_service.update_grams(out, idx + 1, grams)
        return out

    if n_grams == 1 and n_items > 1:
        g = values[0]
        pos = positions[0]
        item_idx = _best_item_index_for_lone_gram(user_text, out.items, pos) + 1
        if abs(out.items[item_idx - 1].estimated_grams - g) > 1e-6:
            out = calorie_service.update_grams(out, item_idx, g)
        return out

    return result
