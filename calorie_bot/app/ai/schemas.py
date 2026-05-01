from typing import Literal

from pydantic import BaseModel, Field


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


class FoodItemRecognition(BaseModel):
    """Validated AI recognition result for a single food item."""

    name: str = Field(min_length=1)
    portion_description: str = Field(min_length=1)
    estimated_grams: float = Field(ge=0)
    calories: int = Field(ge=0)
    protein: float | None = Field(default=None, ge=0)
    fat: float | None = Field(default=None, ge=0)
    carbs: float | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0, le=1)


class FoodRecognitionResult(BaseModel):
    """Validated AI recognition result for a meal photo."""

    items: list[FoodItemRecognition] = Field(min_length=1)
    total_calories: int = Field(ge=0)
    overall_confidence: float = Field(ge=0, le=1)
    comment: str = Field(min_length=1)
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] | None = None
    needs_clarification: bool = False
    clarification_question: str | None = None


class FoodNutritionEstimateSchema(BaseModel):
    """AI nutrition estimate for a food per 100 grams."""

    display_name: str = Field(min_length=1)
    calories_per_100g: float = Field(ge=0, le=5000)
    protein_per_100g: float | None = Field(default=None, ge=0)
    fat_per_100g: float | None = Field(default=None, ge=0)
    carbs_per_100g: float | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0, le=1)
