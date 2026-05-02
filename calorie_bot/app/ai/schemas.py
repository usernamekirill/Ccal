from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from calorie_bot.app.domain import GramsSource


class MealItemAnalysis(BaseModel):
    """Structured AI result for one recognized food item."""

    name: str
    portion_text: str | None = None
    grams: float | None = None
    calories: int = Field(ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)


class MealAnalysis(BaseModel):
    """Structured AI result for a meal photo or text correction."""

    items: list[MealItemAnalysis]
    total_calories: int = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    notes: str | None = None


class VisionPhotoAnalysisItem(BaseModel):
    """Raw vision model output: nutrition per 100g + portion guess, no final calories."""

    name: str = Field(min_length=1)
    portion_description: str | None = None
    estimated_grams: float | None = Field(default=None, ge=0)
    grams_min: float | None = Field(default=None, ge=0)
    grams_max: float | None = Field(default=None, ge=0)
    calories_per_100g: float | None = Field(default=None, ge=0, le=5000)
    protein_per_100g: float | None = Field(default=None, ge=0)
    fat_per_100g: float | None = Field(default=None, ge=0)
    carbs_per_100g: float | None = Field(default=None, ge=0)
    food_confidence: float | None = Field(default=None, ge=0, le=1)
    portion_confidence: float | None = Field(default=None, ge=0, le=1)


class VisionPhotoAnalysisResult(BaseModel):
    """Raw JSON from the photo vision prompt before CalorieService merges portions."""

    items: list[VisionPhotoAnalysisItem] = Field(min_length=1)
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] | None = None
    overall_confidence: float | None = Field(default=None, ge=0, le=1)
    comment: str | None = None


class FoodItemRecognition(BaseModel):
    """Validated recognition result for a single food item (Telegram + persistence)."""

    name: str = Field(min_length=1)
    portion_description: str = Field(min_length=1)
    estimated_grams: float | None = Field(default=None, ge=0)
    grams_min: float | None = Field(default=None, ge=0)
    grams_max: float | None = Field(default=None, ge=0)
    calories: int | None = Field(default=None, ge=0)
    calories_min: int | None = Field(default=None, ge=0)
    calories_max: int | None = Field(default=None, ge=0)
    calories_per_100g: float | None = Field(default=None, ge=0, le=5000)
    protein_per_100g: float | None = Field(default=None, ge=0)
    fat_per_100g: float | None = Field(default=None, ge=0)
    carbs_per_100g: float | None = Field(default=None, ge=0)
    protein: float | None = Field(default=None, ge=0)
    fat: float | None = Field(default=None, ge=0)
    carbs: float | None = Field(default=None, ge=0)
    protein_min: float | None = Field(default=None, ge=0)
    protein_max: float | None = Field(default=None, ge=0)
    fat_min: float | None = Field(default=None, ge=0)
    fat_max: float | None = Field(default=None, ge=0)
    carbs_min: float | None = Field(default=None, ge=0)
    carbs_max: float | None = Field(default=None, ge=0)
    food_confidence: float = Field(default=0.7, ge=0, le=1)
    portion_confidence: float = Field(default=0.5, ge=0, le=1)
    grams_source: Literal[
        "user",
        "user_quantity",
        "voice_correction",
        "text_correction",
        "ai_photo",
        "default_portion",
        "unknown",
    ] = "unknown"
    needs_portion_clarification: bool = False
    is_estimated: bool = True
    confidence: float = Field(default=0.7, ge=0, le=1)
    quantity: float | None = Field(default=None, ge=0)
    unit_type: str | None = None
    unit_weight_grams: float | None = Field(default=None, ge=0)
    size_modifier: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_item(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "portion_description" not in out and out.get("portion_text"):
            out["portion_description"] = str(out.pop("portion_text"))
        if not str(out.get("portion_description", "")).strip():
            out["portion_description"] = "порция"
        if "food_confidence" not in out and out.get("confidence") is not None:
            out["food_confidence"] = out["confidence"]
        if "portion_confidence" not in out and out.get("confidence") is not None:
            out["portion_confidence"] = out["confidence"]
        if out.get("estimated_grams") is None and out.get("grams") is not None:
            out["estimated_grams"] = out.get("grams")
        if out.get("grams_source") is None:
            conf_raw = out.get("confidence")
            conf_val = float(conf_raw) if conf_raw is not None else 1.0
            if conf_val >= 0.95 and out.get("estimated_grams"):
                out["grams_source"] = GramsSource.AI_PHOTO.value
            else:
                out["grams_source"] = GramsSource.UNKNOWN.value

        def _float_or(key: str, default: float) -> float:
            v = out.get(key, default)
            if v is None:
                return default
            return float(v)

        fc = _float_or("food_confidence", 0.7)
        pc = _float_or("portion_confidence", 0.5)
        out["food_confidence"] = fc
        out["portion_confidence"] = pc
        out["confidence"] = min(fc, pc)
        return out


class FoodRecognitionResult(BaseModel):
    """Validated AI recognition result for a meal photo or text."""

    items: list[FoodItemRecognition] = Field(min_length=1)
    total_calories: int = Field(ge=0)
    total_calories_min: int | None = Field(default=None, ge=0)
    total_calories_max: int | None = Field(default=None, ge=0)
    overall_confidence: float = Field(ge=0, le=1)
    comment: str = Field(min_length=1)
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] | None = None
    needs_clarification: bool = False
    clarification_question: str | None = None
    needs_portion_clarification: bool = False
    has_estimated_items: bool = False

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_result(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "needs_portion_clarification" not in out:
            out["needs_portion_clarification"] = any(
                bool(i.get("needs_portion_clarification"))
                for i in out.get("items") or []
                if isinstance(i, dict)
            )
        if not str(out.get("comment", "")).strip():
            out["comment"] = "Оценка приёма пищи"
        if "has_estimated_items" not in out:
            out["has_estimated_items"] = any(
                bool(i.get("is_estimated", True)) for i in out.get("items") or [] if isinstance(i, dict)
            )
        return out


class FoodNutritionEstimateSchema(BaseModel):
    """AI nutrition estimate for a food per 100 grams."""

    display_name: str = Field(min_length=1)
    calories_per_100g: float = Field(ge=0, le=5000)
    protein_per_100g: float | None = Field(default=None, ge=0)
    fat_per_100g: float | None = Field(default=None, ge=0)
    carbs_per_100g: float | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0, le=1)
