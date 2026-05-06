"""Rule-based clarification priority and context (before/after AI copy)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.services.nutrition_calculator import has_quantified_portion_mass
from calorie_bot.app.utils.food_emoji import food_line_emoji

PrimaryIssue = Literal[
    "missing_weight",
    "ambiguous_product",
    "low_confidence",
    "unknown_items",
    "other",
]


@dataclass(frozen=True)
class ClarificationLLMContext:
    """Structured payload for one-shot clarification generation (AI assistant UX)."""

    dish_line: str
    dish_emoji: str
    recognized_items: list[dict[str, object]]
    primary_issue: PrimaryIssue
    missing_fields: list[str]
    prior_model_question: str | None
    overall_confidence: float


_DAIRY = ("творог", "йогурт", "кефир", "ряженк", "сметан", "творожок", "снежок")
_SOUP = ("суп", "борщ", "бульон", "уха", "солянк")
_CAKE = ("шарлот", "торт", "пирог", "кекс", "бисквит", "чизкейк")
_PASTA = ("макарон", "паста", "спагетти", "лапш", "вермишел")
_MEAT = ("куриц", "индейк", "говядин", "свинин", "рыб", "котлет", "бифштекс")


def portion_presets_for_dish(dish_line: str) -> list[tuple[int, str]]:
    """Typical gram presets + short Russian labels (contextual, not generic cheese/pasta examples)."""
    raw = (dish_line or "").strip()
    low = raw.lower()
    ne = low.replace("ё", "е")
    if ne == "мед":
        return [(20, ""), (30, ""), (40, "")]
    if any(k in low for k in _DAIRY):
        return [(150, "небольшая порция"), (200, "средняя"), (300, "большая")]
    if any(k in low for k in _SOUP):
        return [(250, "чаша"), (330, "средняя"), (400, "большая")]
    if any(k in low for k in _CAKE):
        return [(100, "тонкий кусок"), (150, "средний"), (200, "щедрый")]
    if any(k in low for k in _PASTA):
        return [(200, "поменьше"), (250, "норма"), (330, "с голоду")]
    if any(k in low for k in _MEAT):
        return [(120, "поменьше"), (180, "средняя порция"), (250, "побольше")]
    return [(100, "поменьше"), (150, "средняя"), (200, "побольше")]


def missing_weight_portion_actions(
    result: FoodRecognitionResult,
) -> list[tuple[int | None, int, str]]:
    """Build preset rows: (item_index, grams, product_name); two gram options per underweighted line."""
    out: list[tuple[int | None, int, str]] = []
    for idx, it in enumerate(result.items):
        if has_quantified_portion_mass(it.estimated_grams, it.grams_min, it.grams_max):
            continue
        name = (it.name or "").strip() or "Позиция"
        n_presets = 3 if len(result.items) == 1 else 2
        for grams, _desc in portion_presets_for_dish(name)[:n_presets]:
            out.append((idx, int(grams), name))
    return out


def build_dish_line(result: FoodRecognitionResult) -> tuple[str, str]:
    """Human dish title + emoji for Telegram (from recognized lines)."""
    if not result.items:
        return ("Блюдо", food_line_emoji("еда"))
    names = [it.name.strip() for it in result.items if (it.name or "").strip()]
    if not names:
        return ("Блюдо", food_line_emoji("еда"))
    if len(names) == 1:
        n = names[0]
        return (n[0].upper() + n[1:] if len(n) > 1 else n.upper(), food_line_emoji(n))
    if len(names) == 2:
        a, b = names[0], names[1]
        titled = f"{a[0].upper() + a[1:]} с {b}"
        return (titled, food_line_emoji(a))
    joined = " и ".join(names)
    return (joined[0].upper() + joined[1:] if joined else joined, food_line_emoji(names[0]))


def classify_primary_issue(
    result: FoodRecognitionResult,
    calorie_service: CalorieService,
) -> PrimaryIssue:
    """Single top-priority issue — drives one user-facing action."""
    if not result.items:
        return "unknown_items"
    ambiguous = any(calorie_service._ambiguous_name_requires_detail(it) for it in result.items)
    missing_mass = any(
        not has_quantified_portion_mass(it.estimated_grams, it.grams_min, it.grams_max)
        for it in result.items
    )
    # Product-specific copy: if mass is unknown, ask portion first (even for generically named items).
    if missing_mass:
        return "missing_weight"
    if ambiguous:
        return "ambiguous_product"
    user_like = (
        "user",
        "user_quantity",
        "text_correction",
        "voice_correction",
    )
    all_pinned = all(
        has_quantified_portion_mass(it.estimated_grams, it.grams_min, it.grams_max)
        and (it.grams_source in user_like)
        for it in result.items
    )
    if calorie_service.is_low_confidence(result) and not all_pinned:
        return "low_confidence"
    return "other"


def build_llm_context(
    result: FoodRecognitionResult,
    calorie_service: CalorieService,
) -> ClarificationLLMContext:
    """Pack recognition state for clarification JSON (no validator string concatenation)."""
    dish, emoji = build_dish_line(result)
    issue = classify_primary_issue(result, calorie_service)
    missing: list[str] = []
    if issue == "missing_weight":
        missing.append("grams")
    if issue == "ambiguous_product":
        missing.append("product_detail")
    if issue == "low_confidence":
        missing.append("confirm_portion")
    if issue == "unknown_items":
        missing.append("what_food")

    items_payload: list[dict[str, object]] = []
    for it in result.items:
        items_payload.append(
            {
                "name": it.name,
                "has_grams": has_quantified_portion_mass(
                    it.estimated_grams, it.grams_min, it.grams_max
                ),
                "needs_portion_clarification": it.needs_portion_clarification,
            }
        )

    prior = (result.clarification_question or "").strip() or None
    return ClarificationLLMContext(
        dish_line=dish,
        dish_emoji=emoji,
        recognized_items=items_payload,
        primary_issue=issue,
        missing_fields=missing,
        prior_model_question=prior,
        overall_confidence=float(result.overall_confidence),
    )


def multi_item_missing_weight_clarification_body(ctx: ClarificationLLMContext) -> str | None:
    """Structured copy for compound dishes (no «общий вес творога и мёда»)."""
    if len(ctx.recognized_items) < 2:
        return None
    missing = [it for it in ctx.recognized_items if not bool(it.get("has_grams"))]
    if not missing:
        return None
    title = f"{ctx.dish_emoji} {ctx.dish_line}"
    bullets = "\n".join(
        f"• {str(it.get('name') or 'Позиция').strip()} — сколько граммов?" for it in missing
    )
    return (
        f"{title}\n\n"
        "Уточните порции:\n"
        f"{bullets}\n\n"
        "Можно написать одной фразой:\n"
        "«творог 180 г, мёд 20 г»"
    )


def fallback_clarification_body(ctx: ClarificationLLMContext) -> str:
    """Local copy if OpenAI fails — still one action, no unrelated examples."""
    title = f"{ctx.dish_emoji} {ctx.dish_line}"
    if ctx.primary_issue == "missing_weight":
        multi = multi_item_missing_weight_clarification_body(ctx)
        if multi:
            return multi
        return (
            f"{title}\n\n"
            "Сколько примерно было?\n\n"
            "Выбери вариант ниже или напиши вес одним сообщением ✍️"
        )
    if ctx.primary_issue == "ambiguous_product":
        return (
            f"{title}\n\n"
            "Нужно чуть конкретики по одному продукту — напиши одним сообщением, что именно имелось в виду ✍️"
        )
    if ctx.primary_issue == "unknown_items":
        return "Опиши, пожалуйста, что съел одной короткой фразой — с названиями блюд ✍️"
    return (
        f"{title}\n\n"
        "Чтобы точнее посчитать калории, напиши порцию (граммы или «тарелка», «кусок») ✍️"
    )


def should_omit_clarification_footer_in_review(
    result: FoodRecognitionResult,
    calorie_service: CalorieService,
) -> bool:
    """Avoid duplicate clarification lines on the meal card when we already ask for one thing."""
    if not result.items:
        return False
    if classify_primary_issue(result, calorie_service) != "missing_weight":
        return False
    return not any(calorie_service._ambiguous_name_requires_detail(it) for it in result.items)
