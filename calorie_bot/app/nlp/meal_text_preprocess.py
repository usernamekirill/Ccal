"""NLP layer for meal text: normalize → weights → offline single-line parse (no LLM).

Pipeline (design targets from product spec; реализация частично rule-based, частично LLM):

1. **normalize_text** — ``normalize_meal_input_text`` (NFKC, ё, пробелы, буква↔цифра).
2. **extract_quantity** — ``apply_user_quantity_from_text`` / quantity phrase (после нормализации строки).
3. **extract_weight** — ``extract_ordered_gram_values`` / ``_GRAM_PATTERN`` в ``food_parser_service``.
4. **extract_food_entities** / **map_to_canonical_name** — номинатив: ``canonicalize_food_phrase``; полное мульти-item — LLM.
5. **validate** / **calculate** — ``CalorieService.validate_food_result``, hydrate, Atwater — без изменений контракта.

Функция ``try_parse_plaintext_meal_line`` закрывает один продукт с явной массой и кейсы уточнения до вызова OpenAI.
"""

from __future__ import annotations

import re
import unicodedata

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.domain import GramsSource

# Типовые формы продукта в родительном/дательном → номинатив (без полноценной pymorphy)
_FOOD_FORM_TO_NOMINATIVE: dict[str, str] = {
    "гречки": "гречка",
    "гречке": "гречка",
    "шарлотки": "шарлотка",
    "шарлотке": "шарлотка",
    "курицы": "курица",
    "курице": "курица",
    "риса": "рис",
    "рису": "рис",
    "банана": "банан",
    "банану": "банан",
    "яблока": "яблоко",
    "яблок": "яблоко",
    "яиц": "яйцо",
    "яйца": "яйцо",
    "яйцо": "яйцо",
    "сметаны": "сметана",
    "сметане": "сметана",
    "сыра": "сыр",
    "сыру": "сыр",
    "молока": "молоко",
    "молоку": "молоко",
    "грудки": "грудка",
    "колбасы": "колбаса",
    "овсянки": "овсянка",
    "овсянке": "овсянка",
}

_GRAMS_ONLY_LINE = re.compile(
    r"^\s*(\d+(?:[.,]\d+)?)\s*(?:г(?:рамм?(?:ов|а|е)?)?|гр)\s*$",
    re.IGNORECASE | re.UNICODE,
)

_BARE_NUMBER_AFTER_FOOD = re.compile(
    r"^([а-яёa-z])([а-яёa-z\s\-]{0,78}[а-яёa-z])\s+(\d+(?:[.,]\d+)?)\s*$",
    re.UNICODE,
)


def normalize_meal_input_text(text: str) -> str:
    """Lowercase NFKC, ё→е, пробелы, разделение «слоёв» буква↔цифра (гречка200г)."""
    t = unicodedata.normalize("NFKC", text or "")
    t = t.strip().lower().replace("ё", "е")
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"([а-яa-z])(\d)", r"\1 \2", t)
    t = re.sub(r"(\d)([а-яa-z])", r"\1 \2", t)
    return t.strip()


def canonicalize_food_phrase(name: str) -> str:
    """Подбор номинатива по ограниченному словарю (слово к слову)."""
    if not name or not name.strip():
        return name
    parts = name.split()
    out = [_FOOD_FORM_TO_NOMINATIVE.get(p, p) for p in parts]
    return " ".join(out)


def try_grams_only_clarification(text: str) -> FoodRecognitionResult | None:
    """Только масса без продукта — блокирующее уточнение (спек #9)."""
    if not _GRAMS_ONLY_LINE.match((text or "").strip()):
        return None
    return FoodRecognitionResult(
        items=[],
        total_calories=0,
        overall_confidence=0.5,
        comment="Нужно название продукта к указанной массе.",
        needs_clarification=True,
        clarification_question=(
            "Указана только масса. Напишите продукт целиком, например: «гречка 200 г» или «200 г гречки»."
        ),
    )


def try_bare_number_after_food(text: str) -> FoodRecognitionResult | None:
    """«гречка 200» без единицы — просим подтвердить граммы (спек #8)."""
    from calorie_bot.app.services.calorie_service import normalize_food_name
    from calorie_bot.app.services.food_parser_service import extract_ordered_gram_values

    t = (text or "").strip()
    if not t or extract_ordered_gram_values(t):
        return None
    m = _BARE_NUMBER_AFTER_FOOD.match(t)
    if not m:
        return None
    raw_name = (m.group(1) + m.group(2)).strip()
    num_raw = m.group(3).replace(",", ".")
    try:
        num = float(num_raw)
    except ValueError:
        return None
    if num <= 0 or num > 99_999:
        return None
    name = canonicalize_food_phrase(normalize_food_name(raw_name))
    if len(name) < 2:
        return None
    return FoodRecognitionResult(
        items=[
            FoodItemRecognition(
                name=name,
                portion_description="уточните порцию",
                estimated_grams=None,
                calories=None,
                food_confidence=0.55,
                portion_confidence=0.5,
                grams_source=GramsSource.UNKNOWN.value,
                needs_portion_clarification=True,
                confidence=0.5,
            )
        ],
        total_calories=0,
        overall_confidence=0.5,
        comment="Число без единицы массы.",
        needs_clarification=True,
        clarification_question=(
            f"Вы написали «{name} {num_raw}» без единиц. Это граммы? Ответьте, "
            f"например: «{name} {num_raw} г»."
        ),
    )


def try_parse_plaintext_meal_line(normalized_text: str) -> FoodRecognitionResult | None:
    """Один продукт с явными граммами / только масса / число без «г» — без OpenAI."""
    from calorie_bot.app.services.calorie_service import CalorieService
    from calorie_bot.app.services.food_parser_service import try_simple_gram_meal_text

    t = (normalized_text or "").strip()
    if not t:
        return None
    g = try_grams_only_clarification(t)
    if g is not None:
        return CalorieService().validate_food_result(g)
    b = try_bare_number_after_food(t)
    if b is not None:
        return CalorieService().validate_food_result(b)
    s = try_simple_gram_meal_text(t)
    if s is not None:
        return CalorieService().validate_food_result(s)
    return None
