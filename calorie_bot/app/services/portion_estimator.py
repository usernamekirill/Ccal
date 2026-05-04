"""Typical portion gram ranges when AI or user does not give a confident weight."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Order matters: first substring match in normalized name wins (longer phrases first).
_DEFAULT_PORTION_RULES: tuple[tuple[str, tuple[float, float]], ...] = (
    ("кофе с молоком", (200, 300)),
    ("кофе", (150, 250)),
    ("чай с молоком", (200, 300)),
    ("паста", (200, 300)),
    ("спагетти", (200, 300)),
    ("макароны", (180, 280)),
    ("рис", (150, 220)),
    ("гречк", (150, 200)),
    ("овсянк", (200, 280)),
    ("каша", (200, 300)),
    ("курин", (120, 180)),
    ("мясо", (120, 200)),
    ("рыб", (120, 180)),
    ("стейк", (150, 220)),
    ("суп", (250, 350)),
    ("борщ", (300, 400)),
    ("салат", (150, 250)),
    ("выпечк", (40, 80)),
    ("кулич", (50, 80)),
    ("круассан", (50, 75)),
    ("торт", (80, 150)),
    ("пирожн", (60, 120)),
    ("пирог", (100, 180)),
    ("морожен", (80, 120)),
    ("десерт", (80, 150)),
    ("сыр", (30, 60)),
    ("орех", (20, 40)),
    ("арахис", (20, 40)),
    ("масло сливочн", (10, 20)),
    ("масло", (10, 25)),
    ("соус", (30, 60)),
    ("кетчуп", (20, 40)),
    ("майонез", (20, 40)),
    ("пицц", (150, 250)),
    ("бургер", (200, 320)),
    ("фри", (100, 180)),
    ("картофел", (150, 250)),
    ("хлеб", (30, 50)),
)


@dataclass(frozen=True)
class DefaultPortionRange:
    """Typical min/max grams for a food name."""

    grams_min: float
    grams_max: float


def normalize_food_key(name: str) -> str:
    """Lowercase Russian-friendly key for substring rules."""
    n = name.strip().lower().replace("ё", "е")
    n = re.sub(r"\s+", " ", n)
    return n


def estimate_default_portion_grams(name: str) -> DefaultPortionRange | None:
    """Return a typical portion range for ``name``, or None if unknown."""
    key = normalize_food_key(name)
    for needle, bounds in _DEFAULT_PORTION_RULES:
        if needle in key:
            return DefaultPortionRange(grams_min=bounds[0], grams_max=bounds[1])
    return DefaultPortionRange(grams_min=80, grams_max=150)


def is_calorie_dense_food(name: str) -> bool:
    """Heuristic: foods where wrong portion size matters a lot for calories."""
    key = normalize_food_key(name)
    dense_markers = (
        "выпечк",
        "кулич",
        "круассан",
        "торт",
        "пирожн",
        "десерт",
        "морожен",
        "круп",
        "гречк",
        "рис",
        "паста",
        "макарон",
        "спагетти",
        "овсянк",
        "каша",
        "мяс",
        "куриц",
        "говядин",
        "свинин",
        "рыб",
        "стейк",
        "сыр",
        "орех",
        "арахис",
        "фундук",
        "миндаль",
        "масло",
        "соус",
        "кетчуп",
        "майонез",
        "пицц",
        "бургер",
        "фри",
        "шаурм",
        "ролл",
        "хот-дог",
        "фастфуд",
    )
    return any(m in key for m in dense_markers)
