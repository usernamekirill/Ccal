import re
from dataclasses import dataclass
from typing import Protocol

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.domain import MealDraft, MealItemDraft, MealSource, MealType
from calorie_bot.app.repositories.food_cache_repository import FoodCacheRepository

LOW_CONFIDENCE_THRESHOLD = 0.65
MAX_ITEM_CALORIES = 5000
MAX_ITEM_GRAMS = 5000


@dataclass(frozen=True)
class NutritionEstimate:
    """Nutrition values for a food per 100 grams."""

    display_name: str
    calories_per_100g: float
    protein_per_100g: float | None
    fat_per_100g: float | None
    carbs_per_100g: float | None
    confidence: float
    is_estimated: bool = True


class FoodNutritionEstimator(Protocol):
    """Protocol for AI-backed nutrition estimation."""

    async def estimate_food(self, food_name: str) -> NutritionEstimate:
        """Return nutrition estimate for a normalized food name."""


class CalorieService:
    """Format, recalculate, and edit food recognition results."""

    def to_meal_draft(
        self,
        result: FoodRecognitionResult,
        source: MealSource = MealSource.PHOTO,
    ) -> MealDraft:
        """Convert food recognition result into a confirmable meal draft."""
        items = [
            MealItemDraft(
                name=item.name,
                portion_text=item.portion_description,
                grams=item.estimated_grams,
                calories=item.calories,
                protein_g=item.protein,
                fat_g=item.fat,
                carbs_g=item.carbs,
                confidence=item.confidence,
            )
            for item in result.items
        ]
        normalized_items = [self.validate_item(item) for item in items]
        return MealDraft(
            items=normalized_items,
            total_calories=self.calculate_meal_calories(normalized_items),
            source=source,
            meal_type=MealType(result.meal_type) if result.meal_type else None,
            confidence=result.overall_confidence,
            notes=result.comment,
        )

    def draft_to_result(self, draft: MealDraft) -> FoodRecognitionResult:
        """Convert a stored meal draft into a reviewable recognition result."""
        items = [
            FoodItemRecognition(
                name=item.name,
                portion_description=item.portion_text or _portion_text(item.grams),
                estimated_grams=item.grams or 0,
                calories=item.calories,
                protein=item.protein_g,
                fat=item.fat_g,
                carbs=item.carbs_g,
                confidence=item.confidence or 1,
            )
            for item in draft.items
        ]
        return self.validate_food_result(
            FoodRecognitionResult(
                items=items,
                total_calories=draft.total_calories,
                overall_confidence=draft.confidence or 1,
                comment=draft.notes or "Сохраненный прием пищи",
                meal_type=draft.meal_type.value if draft.meal_type else None,
            )
        )

    def result_to_dict(self, result: FoodRecognitionResult) -> dict:
        """Serialize a recognition result for FSM storage."""
        return result.model_dump(mode="json")

    def result_from_dict(self, data: dict) -> FoodRecognitionResult:
        """Deserialize a recognition result from FSM storage."""
        return FoodRecognitionResult.model_validate(data)

    async def get_or_estimate_food(
        self,
        food_name: str,
        grams: float,
        cache_repository: FoodCacheRepository,
        estimator: FoodNutritionEstimator,
    ) -> FoodItemRecognition:
        """Return food item using cache first, AI estimator second."""
        self.validate_grams(grams)
        normalized_name = normalize_food_name(food_name)
        cached = await cache_repository.get_by_normalized_name(normalized_name)
        if cached is None:
            estimate = await estimator.estimate_food(food_name)
            self.validate_calories(estimate.calories_per_100g)
            cached = await cache_repository.upsert(
                normalized_name=normalized_name,
                display_name=estimate.display_name,
                calories_per_100g=estimate.calories_per_100g,
                protein_per_100g=estimate.protein_per_100g,
                fat_per_100g=estimate.fat_per_100g,
                carbs_per_100g=estimate.carbs_per_100g,
                confidence=estimate.confidence,
                is_estimated=estimate.is_estimated,
            )

        calories = self.calculate_item_calories(cached.calories_per_100g, grams)
        return FoodItemRecognition(
            name=cached.display_name,
            portion_description=f"{grams:.0f} г",
            estimated_grams=grams,
            calories=calories,
            protein=_from_per_100g(cached.protein_per_100g, grams),
            fat=_from_per_100g(cached.fat_per_100g, grams),
            carbs=_from_per_100g(cached.carbs_per_100g, grams),
            confidence=cached.confidence,
        )

    def calculate_item_calories(self, calories_per_100g: float, grams: float) -> int:
        """Calculate calories for an item from per-100g value and grams."""
        self.validate_calories(calories_per_100g)
        self.validate_grams(grams)
        calories = round(calories_per_100g * grams / 100)
        self.validate_calories(calories)
        return calories

    def calculate_meal_calories(self, items: list[MealItemDraft]) -> int:
        """Calculate total meal calories from items."""
        for item in items:
            self.validate_item(item)
        return sum(item.calories for item in items)

    def validate_item(self, item: MealItemDraft) -> MealItemDraft:
        """Validate item calories, grams, macros, and confidence."""
        self.validate_calories(item.calories)
        if item.grams is not None:
            self.validate_grams(item.grams)
        _validate_optional_non_negative(item.protein_g, "protein")
        _validate_optional_non_negative(item.fat_g, "fat")
        _validate_optional_non_negative(item.carbs_g, "carbs")
        if item.confidence is not None and not 0 <= item.confidence <= 1:
            raise ValueError("confidence_must_be_between_0_and_1")
        return item

    def validate_food_result(self, result: FoodRecognitionResult) -> FoodRecognitionResult:
        """Validate and normalize a recognition result."""
        for item in result.items:
            self.validate_calories(item.calories)
            self.validate_grams(item.estimated_grams)
            item.name = normalize_food_name(item.name)
            _validate_optional_non_negative(item.protein, "protein")
            _validate_optional_non_negative(item.fat, "fat")
            _validate_optional_non_negative(item.carbs, "carbs")
        result.total_calories = sum(item.calories for item in result.items)
        return FoodRecognitionResult.model_validate(result.model_dump())

    def with_default_meal_type(
        self,
        result: FoodRecognitionResult,
        meal_type: MealType,
    ) -> FoodRecognitionResult:
        """Set meal type when parser did not detect it."""
        if result.meal_type is None:
            result.meal_type = meal_type.value
        return FoodRecognitionResult.model_validate(result.model_dump())

    def update_meal_type(
        self,
        result: FoodRecognitionResult,
        meal_type: MealType,
    ) -> FoodRecognitionResult:
        """Update meal type selected by the user."""
        result.meal_type = meal_type.value
        return FoodRecognitionResult.model_validate(result.model_dump())

    def format_saved_meal_brief(self, result: FoodRecognitionResult) -> str:
        """Compact summary after the user saved a meal (no edit-mode hints)."""
        result = self.validate_food_result(result)
        lines = ["🍽 Что сохранили:"]
        for index, item in enumerate(result.items, start=1):
            lines.append(f"{index}. {item.name} — {item.calories} ккал")
        lines.append(f"Итого приёма: {result.total_calories} ккал")
        return "\n".join(lines)

    def format_result(self, result: FoodRecognitionResult) -> str:
        """Return a user-facing recognition summary."""
        result = self.validate_food_result(result)
        lines = ["Смотрю на результат. Проверьте, пожалуйста:\n"]
        for index, item in enumerate(result.items, start=1):
            macros = self._format_macros(item)
            lines.append(
                f"{index}. {item.name} — {item.portion_description}, "
                f"{item.estimated_grams:.0f} г, {item.calories} ккал{macros}"
            )
        lines.append(f"\nИтого: {result.total_calories} ккал")
        lines.append(f"Комментарий: {result.comment}")
        lines.append("Расчет примерный — лучше проверить порции перед сохранением.")
        if self.is_low_confidence(result):
            lines.append("\nЯ не совсем уверен, проверьте, пожалуйста.")
        if result.meal_type:
            lines.append(f"\nТип приема: {_meal_type_label(MealType(result.meal_type))}")
        return "\n".join(lines)

    def is_low_confidence(self, result: FoodRecognitionResult) -> bool:
        """Return whether recognition confidence is low."""
        return result.overall_confidence < LOW_CONFIDENCE_THRESHOLD or any(
            item.confidence < LOW_CONFIDENCE_THRESHOLD for item in result.items
        )

    def update_name(
        self,
        result: FoodRecognitionResult,
        index: int,
        name: str,
    ) -> FoodRecognitionResult:
        """Update a recognized item name."""
        item = self._item_at(result, index)
        item.name = normalize_food_name(name)
        return self._rebuild(result)

    def update_grams(
        self,
        result: FoodRecognitionResult,
        index: int,
        grams: float,
    ) -> FoodRecognitionResult:
        """Update grams and proportionally adjust calories and macros."""
        self.validate_grams(grams)
        item = self._item_at(result, index)
        ratio = grams / item.estimated_grams if item.estimated_grams else 1
        item.estimated_grams = grams
        item.calories = round(item.calories * ratio)
        item.protein = _scale_optional(item.protein, ratio)
        item.fat = _scale_optional(item.fat, ratio)
        item.carbs = _scale_optional(item.carbs, ratio)
        return self._rebuild(result)

    def update_calories(
        self,
        result: FoodRecognitionResult,
        index: int,
        calories: int,
    ) -> FoodRecognitionResult:
        """Update calories for a recognized item."""
        self.validate_calories(calories)
        self._item_at(result, index).calories = calories
        return self._rebuild(result)

    def add_item(
        self,
        result: FoodRecognitionResult,
        name: str,
        grams: float,
        calories: int,
    ) -> FoodRecognitionResult:
        """Add a manual item to a recognition result."""
        self.validate_grams(grams)
        self.validate_calories(calories)
        result.items.append(
            FoodItemRecognition(
                name=normalize_food_name(name),
                portion_description=f"{grams:.0f} г",
                estimated_grams=grams,
                calories=calories,
                protein=None,
                fat=None,
                carbs=None,
                confidence=1,
            )
        )
        return self._rebuild(result)

    def delete_item(self, result: FoodRecognitionResult, index: int) -> FoodRecognitionResult:
        """Delete a recognized item."""
        self._item_at(result, index)
        del result.items[index - 1]
        return self._rebuild(result)

    def recalculate_total(self, items: list[MealItemDraft]) -> int:
        """Recalculate total calories from items."""
        return self.calculate_meal_calories(items)

    def validate_calories(self, calories: float) -> None:
        """Validate calories against realistic per-item bounds."""
        if calories < 0:
            raise ValueError("calories_cannot_be_negative")
        if calories > MAX_ITEM_CALORIES:
            raise ValueError("item_calories_too_high")

    def validate_grams(self, grams: float) -> None:
        """Validate grams against realistic per-item bounds."""
        if grams < 0:
            raise ValueError("grams_cannot_be_negative")
        if grams > MAX_ITEM_GRAMS:
            raise ValueError("item_grams_too_high")

    def _rebuild(self, result: FoodRecognitionResult) -> FoodRecognitionResult:
        result = self.validate_food_result(result)
        result.total_calories = sum(item.calories for item in result.items)
        if result.items:
            result.overall_confidence = min(item.confidence for item in result.items)
        return FoodRecognitionResult.model_validate(result.model_dump())

    def _item_at(self, result: FoodRecognitionResult, index: int) -> FoodItemRecognition:
        if index < 1 or index > len(result.items):
            raise ValueError("item_index_out_of_range")
        return result.items[index - 1]

    def _format_macros(self, item: FoodItemRecognition) -> str:
        values = []
        if item.protein is not None:
            values.append(f"Б {item.protein:.0f}")
        if item.fat is not None:
            values.append(f"Ж {item.fat:.0f}")
        if item.carbs is not None:
            values.append(f"У {item.carbs:.0f}")
        return f" ({', '.join(values)} г)" if values else ""


def _scale_optional(value: float | None, ratio: float) -> float | None:
    return round(value * ratio, 1) if value is not None else None


def _portion_text(grams: float | None) -> str:
    return f"{grams:.0f} г" if grams is not None else "порция"


def _from_per_100g(value: float | None, grams: float) -> float | None:
    return round(value * grams / 100, 1) if value is not None else None


def _validate_optional_non_negative(value: float | None, field_name: str) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{field_name}_cannot_be_negative")


def normalize_food_name(name: str) -> str:
    """Normalize food names for display and cache lookup."""
    normalized = name.strip().lower().replace("ё", "е")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[^0-9a-zа-я\s-]", "", normalized)
    return normalized.strip()


def _meal_type_label(meal_type: MealType) -> str:
    labels = {
        MealType.BREAKFAST: "завтрак",
        MealType.LUNCH: "обед",
        MealType.DINNER: "ужин",
        MealType.SNACK: "перекус",
    }
    return labels[meal_type]
