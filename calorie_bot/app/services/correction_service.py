import re

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.domain import MealDraft, MealItemDraft, MealSource

CALORIE_PATTERN = re.compile(r"(?P<name>[а-яa-z\s]+)\s+(?P<calories>\d{2,5})\s*(?:ккал)?", re.I)
GRAM_CORRECTION_PATTERN = re.compile(
    r"(?P<name>[а-яa-zё\s]+?)\s+.*?(?:не\s+)?(?P<old>\d{1,4})\s*грамм[а-я]*"
    r".*?(?:а|на)\s+(?P<new>\d{1,4})",
    re.I,
)
ADD_PATTERN = re.compile(r"(?:добавь|добавить|ещ[её])\s+(?P<name>[а-яa-zё\s]+)", re.I)
DELETE_PATTERN = re.compile(r"(?:удали|убери)\s+(?P<name>[а-яa-zё\s]+)", re.I)


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

        return MealDraft(
            items=items,
            total_calories=sum(item.calories for item in items),
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

        delete_match = DELETE_PATTERN.search(normalized)
        if delete_match:
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
                        portion_description="добавлено голосом",
                        estimated_grams=0,
                        calories=0,
                        protein=None,
                        fat=None,
                        carbs=None,
                        confidence=0.5,
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
    ratio = new_grams / item.estimated_grams if item.estimated_grams else 1
    item.estimated_grams = new_grams
    item.portion_description = f"{new_grams:.0f} г"
    item.calories = round(item.calories * ratio)
    item.protein = _scale_optional(item.protein, ratio)
    item.fat = _scale_optional(item.fat, ratio)
    item.carbs = _scale_optional(item.carbs, ratio)


def _recalculate_result(result: FoodRecognitionResult) -> FoodRecognitionResult:
    result.total_calories = sum(item.calories for item in result.items)
    if result.items:
        result.overall_confidence = min(item.confidence for item in result.items)
    else:
        result.overall_confidence = 0
    return FoodRecognitionResult.model_validate(result.model_dump())


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
