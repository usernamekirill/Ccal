import re

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.domain import MealDraft, MealItemDraft, MealSource
from calorie_bot.app.services.calorie_service import CalorieService, meal_draft_calorie_totals

CALORIE_PATTERN = re.compile(r"(?P<name>[а-яa-z\s]+)\s+(?P<calories>\d{2,5})\s*(?:ккал)?", re.I)
GRAM_CORRECTION_PATTERN = re.compile(
    r"(?P<name>[а-яa-zё\s]+?)\s+.*?(?:не\s+)?(?P<old>\d{1,4})\s*грамм[а-я]*"
    r".*?(?:а|на)\s+(?P<new>\d{1,4})",
    re.I,
)
ADD_PATTERN = re.compile(r"(?:добавь|добавить|ещ[её])\s+(?P<name>[а-яa-zё\s]+)", re.I)
DELETE_PATTERN = re.compile(r"(?:удали|убери)\s+(?P<name>[а-яa-zё\s]+)", re.I)
DELETE_ORDINAL_PATTERN = re.compile(r"(?:удали|убери)\s+(?P<ref>[а-яёa-z\d]+)", re.I)

# Russian ordinals / numeric positions (1-based speech → 0-based index).
_ORDINAL_WORD_TO_INDEX: dict[str, int] = {
    "первое": 0,
    "первый": 0,
    "первую": 0,
    "первого": 0,
    "первом": 0,
    "второе": 1,
    "второй": 1,
    "вторую": 1,
    "второго": 1,
    "втором": 1,
    "третье": 2,
    "третий": 2,
    "третью": 2,
    "третьего": 2,
    "третьем": 2,
    "четвертое": 3,
    "четвёртое": 3,
    "четвертый": 3,
    "четвёртый": 3,
    "четвертую": 3,
    "четвёртую": 3,
    "пятое": 4,
    "пятый": 4,
    "пятую": 4,
    "пятого": 4,
    "пятом": 4,
}


def _ordinal_delete_index(ref: str) -> int | None:
    """Map «второе» / «2» to a 0-based item index, or None if not an ordinal token."""
    cleaned = ref.strip().lower().strip(" ,.!")
    if cleaned.isdigit():
        idx = int(cleaned) - 1
        return idx if idx >= 0 else None
    return _ORDINAL_WORD_TO_INDEX.get(cleaned)


class CorrectionService:
    """Apply text or transcribed voice corrections to meal drafts."""

    def apply_text(self, current: MealDraft | None, text: str) -> MealDraft:
        """Apply a compact MVP correction to a meal draft."""
        parsed_item = self._parse_item(text)
        if parsed_item is None and current is not None:
            return current
        if parsed_item is None:
            parsed_item = MealItemDraft(name=text.strip(), calories=0)

        items = list(current.items) if current else []
        if _is_add_command(text) or not items:
            items.append(parsed_item)
        else:
            items[-1] = parsed_item

        tc, tc_min, tc_max = meal_draft_calorie_totals(items)
        return MealDraft(
            items=items,
            total_calories=tc,
            total_calories_min=tc_min,
            total_calories_max=tc_max,
            has_estimated_items=any(i.is_estimated for i in items),
            source=MealSource.TEXT if current is None else MealSource.MIXED,
            confidence=current.confidence if current else None,
            notes=current.notes if current else None,
        )

    def _parse_item(self, text: str) -> MealItemDraft | None:
        match = CALORIE_PATTERN.search(_strip_add_command(text))
        if match is None:
            return None
        return MealItemDraft(
            name=match.group("name").strip(),
            calories=int(match.group("calories")),
            portion_text=None,
        )

    def apply_food_result_correction(
        self,
        current: FoodRecognitionResult,
        correction_text: str,
    ) -> FoodRecognitionResult:
        """Apply a natural-language correction to a photo recognition result."""
        updated = current.model_copy(deep=True)
        normalized = correction_text.lower()
        changed = False

        gram_match = GRAM_CORRECTION_PATTERN.search(normalized)
        if gram_match:
            item = _find_item_by_name(updated, gram_match.group("name"))
            if item is not None:
                _rescale_item(item, float(gram_match.group("new")))
                changed = True

        ord_del = DELETE_ORDINAL_PATTERN.search(normalized)
        ordinal_removed = False
        if ord_del:
            idx = _ordinal_delete_index(ord_del.group("ref"))
            if idx is not None and 0 <= idx < len(updated.items):
                del updated.items[idx]
                changed = True
                ordinal_removed = True

        delete_match = DELETE_PATTERN.search(normalized)
        if delete_match and not ordinal_removed:
            item_index = _find_item_index_by_name(updated, delete_match.group("name"))
            if item_index is not None:
                del updated.items[item_index]
                changed = True

        add_match = ADD_PATTERN.search(normalized)
        if add_match:
            name = _clean_food_name(add_match.group("name"))
            if name:
                updated.items.append(
                    FoodItemRecognition(
                        name=name,
                        portion_description="уточните порцию — например: «150 г» или «200 мл»",
                        estimated_grams=None,
                        grams_min=None,
                        grams_max=None,
                        calories=None,
                        calories_min=None,
                        calories_max=None,
                        calories_per_100g=None,
                        protein=None,
                        fat=None,
                        carbs=None,
                        food_confidence=0.55,
                        portion_confidence=0.25,
                        grams_source="unknown",
                        needs_portion_clarification=True,
                        is_estimated=True,
                        confidence=0.55,
                    )
                )
                changed = True

        if not changed:
            updated.comment = f"{updated.comment} Правку не удалось применить автоматически."
            updated.overall_confidence = min(updated.overall_confidence, 0.5)

        return _recalculate_result(updated)


def _is_add_command(text: str) -> bool:
    normalized = text.lower()
    return normalized.startswith("добав") or normalized.startswith("еще") or "ещё" in normalized


def _strip_add_command(text: str) -> str:
    normalized = text.strip()
    lowered = normalized.lower()
    for prefix in ("добавь", "добавить", "еще", "ещё"):
        if lowered.startswith(prefix):
            return normalized[len(prefix) :].strip()
    return normalized


def _find_item_by_name(result: FoodRecognitionResult, raw_name: str) -> FoodItemRecognition | None:
    item_index = _find_item_index_by_name(result, raw_name)
    return result.items[item_index] if item_index is not None else None


def _find_item_index_by_name(result: FoodRecognitionResult, raw_name: str) -> int | None:
    target_words = {_normalize_food_word(word) for word in _clean_food_name(raw_name).split()}
    if not target_words:
        return None
    for index, item in enumerate(result.items):
        item_words = {_normalize_food_word(word) for word in item.name.lower().split()}
        normalized_name = " ".join(item_words)
        if target_words & item_words or any(word in normalized_name for word in target_words):
            return index
    return None


def _rescale_item(item: FoodItemRecognition, new_grams: float) -> None:
    base = float(item.estimated_grams) if item.estimated_grams is not None else float(
        ((item.grams_min or 0) + (item.grams_max or 0)) / 2 or 1,
    )
    ratio = new_grams / base if base else 1
    item.estimated_grams = new_grams
    item.grams_min = None
    item.grams_max = None
    item.portion_description = f"{new_grams:.0f} г"
    item.calories_min = None
    item.calories_max = None
    if item.calories_per_100g is not None:
        c100 = item.calories_per_100g
        item.calories = round(c100 * new_grams / 100)
        item.protein = (
            round((item.protein_per_100g or 0) * new_grams / 100, 1) if item.protein_per_100g else None
        ) or None
        item.fat = round((item.fat_per_100g or 0) * new_grams / 100, 1) if item.fat_per_100g else None
        item.carbs = (
            round((item.carbs_per_100g or 0) * new_grams / 100, 1) if item.carbs_per_100g else None
        ) or None
    elif item.calories is not None:
        item.calories = max(0, round(item.calories * ratio))
        item.protein = _scale_optional(item.protein, ratio)
        item.fat = _scale_optional(item.fat, ratio)
        item.carbs = _scale_optional(item.carbs, ratio)


def _recalculate_result(result: FoodRecognitionResult) -> FoodRecognitionResult:
    return CalorieService().validate_food_result(result)


def _clean_food_name(value: str) -> str:
    stop_words = {"и", "а", "было", "был", "была", "не", "грамм", "грамма", "граммов"}
    words = [word for word in value.strip().split() if word not in stop_words]
    return " ".join(words).strip(" ,.")


def _normalize_food_word(value: str) -> str:
    word = value.strip(" ,.").lower()
    if len(word) > 3 and word.endswith(("а", "у", "ом", "е")):
        return word.removesuffix("ом").removesuffix("а").removesuffix("у").removesuffix("е")
    return word


def _scale_optional(value: float | None, ratio: float) -> float | None:
    return round(value * ratio, 1) if value is not None else None
