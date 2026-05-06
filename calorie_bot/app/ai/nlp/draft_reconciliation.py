"""Post-LLM checks for meal draft reconciliation (user text > vision; entities preserved)."""

from __future__ import annotations

import logging
import re
from typing import Iterable

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.services.calorie_service import CalorieService, normalize_food_name

_log = logging.getLogger(__name__)

# Minimal RU stopwords for fallback token mining (not meal parsing).
_STOP: frozenset[str] = frozenset(
    {
        "и",
        "в",
        "во",
        "на",
        "по",
        "с",
        "со",
        "из",
        "к",
        "ко",
        "от",
        "до",
        "за",
        "для",
        "без",
        "не",
        "ни",
        "а",
        "но",
        "или",
        "же",
        "ли",
        "бы",
        "то",
        "как",
        "что",
        "это",
        "вот",
        "уже",
        "ещё",
        "еще",
        "там",
        "тут",
        "где",
        "при",
        "про",
        "над",
        "под",
        "мне",
        "мой",
        "моя",
        "моё",
        "твой",
        "его",
        "ее",
        "ещё",
        "раз",
        "два",
        "две",
        "тебе",
        "меня",
        "гр",
        "грамм",
        "грамма",
        "граммов",
        "шт",
        "штук",
        "штуки",
        "порции",
        "порций",
        "порция",
        "кусок",
        "куска",
        "куски",
        "кусочков",
        "две",
        "три",
        "четыре",
        "пять",
        "six",
    }
)


def _normalized(s: str) -> str:
    return normalize_food_name((s or "").strip().lower())


def _term_in_item(term: str, item: FoodItemRecognition) -> bool:
    t = _normalized(term)
    if len(t) < 3:
        return True
    blob = f"{item.name} {item.portion_description}".lower()
    nb = _normalized(item.name)
    if t in blob or t in nb:
        return True
    if len(t) > 4 and (t[:-1] in nb or t[:-1] in blob):
        return True
    if len(t) > 5 and (t[:-2] in nb or t[:-2] in blob):
        return True
    return False


def _term_matches_any_item(term: str, items: Iterable[FoodItemRecognition]) -> bool:
    return any(_term_in_item(term, it) for it in items)


def salient_terms_from_user_text(normalized_user_text: str) -> list[str]:
    """Very light token split for validation fallback (not a meal parser)."""
    if not (normalized_user_text or "").strip():
        return []
    raw = re.sub(r"[^\w\s\-]", " ", normalized_user_text.lower())
    parts = [p for p in raw.split() if len(p) >= 4 and p not in _STOP]
    seen: list[str] = []
    for p in parts:
        if p not in seen:
            seen.append(p)
    return seen[:12]


def collect_user_product_terms(*, model_user_named_products: list[str] | None) -> list[str]:
    """Use LLM-echoed product names only (avoids false rejects on rich phrases)."""
    out: list[str] = []
    for src in model_user_named_products or []:
        s = (src or "").strip()
        if len(s) >= 2 and s.lower() not in out:
            out.append(s.lower())
    return out


def collect_user_product_terms_lenient(
    *,
    user_message_normalized: str,
    model_user_named_products: list[str] | None,
) -> list[str]:
    """Strict list from the model, else light token fallback (tests / legacy payloads)."""
    strict = collect_user_product_terms(model_user_named_products=model_user_named_products)
    if strict:
        return strict
    return salient_terms_from_user_text(user_message_normalized)


def _duplicate_item_keys(items: list[FoodItemRecognition]) -> bool:
    seen: set[tuple[str, float]] = set()
    for it in items:
        g = float(it.estimated_grams) if it.estimated_grams is not None else -1.0
        key = (_normalized(it.name), round(g, 1))
        if key in seen:
            return True
        seen.add(key)
    return False


def apply_reconciliation_validators(
    *,
    user_message_raw: str,
    user_message_normalized: str | None,
    calorie_service: CalorieService,
    structured_user_named_products: list[str] | None,
    fr: FoodRecognitionResult,
) -> FoodRecognitionResult:
    """Ensure user-mentioned products appear in items; drop obvious duplicate lines."""
    um = user_message_normalized or user_message_raw
    terms = collect_user_product_terms_lenient(
        user_message_normalized=um,
        model_user_named_products=structured_user_named_products,
    )

    fr = calorie_service.validate_food_result(fr)

    if not fr.items:
        if terms:
            hint = ", ".join(sorted(set(terms)))
            return calorie_service.validate_food_result(
                FoodRecognitionResult(
                    items=[],
                    total_calories=0,
                    overall_confidence=0.45,
                    comment=fr.comment,
                    meal_type=fr.meal_type,
                    needs_clarification=True,
                    clarification_question=(
                        f"Не удалось оформить позиции для: {hint}. Уточните блюдо и порцию."
                    ),
                )
            )
        return fr

    if fr.items and terms:
        missing = [t for t in terms if not _term_matches_any_item(t, fr.items)]
        if missing:
            _log.info(
                "draft_reconciliation_entity_mismatch",
                extra={"missing": missing, "terms": terms},
            )
            hint = ", ".join(sorted(set(missing)))
            q = (
                f"В черновике не отразились продукты из вашей фразы ({hint}). "
                "Уточните название одной строкой или повторите правку."
            )
            return calorie_service.validate_food_result(
                fr.model_copy(
                    update={
                        "needs_clarification": True,
                        "clarification_question": q,
                    }
                )
            )

    if fr.items and _duplicate_item_keys(fr.items):
        return calorie_service.validate_food_result(
            fr.model_copy(
                update={
                    "needs_clarification": True,
                    "clarification_question": (
                        "Похоже на дублирующиеся позиции с одинаковым названием. "
                        "Уточните порции или объедините в одну строку."
                    ),
                }
            )
        )

    return fr
