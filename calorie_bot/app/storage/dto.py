"""Plain data carriers for storage backends (no ORM / SQL in consumers)."""

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class MealItemDTO:
    """One food line item attached to a meal."""

    name: str
    grams: float | None
    calories: int
    portion_text: str | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbs_g: float | None = None


@dataclass
class MealDTO:
    """Meal as seen by storage (confirmed or draft)."""

    user_id: int
    eaten_at: datetime
    calories: int
    source: str
    meal_type: str | None = None
    status: str = "confirmed"
    id: int | None = None
    protein_g: float = 0.0
    fat_g: float = 0.0
    carbs_g: float = 0.0
    ai_confidence: float | None = None
    is_deleted: bool = False
    items: list[MealItemDTO] = field(default_factory=list)


@dataclass
class UserSettingsDTO:
    """Portable settings blob (profile goal + app settings merged for API clients)."""

    user_id: int
    timezone: str
    calorie_goal: int | None = None
    language: str = "ru"
    notifications_enabled: bool = True
    motivation_enabled: bool = True
    ai_analysis_enabled: bool = True
    measurement_unit: str = "metric"


@dataclass
class DailyAggregateDTO:
    """Denormalized day row (optional materialization in SQL or computed in API)."""

    user_id: int
    day: date
    total_calories: int
    meals_count: int
    calorie_goal: int | None = None
    total_protein_g: float = 0.0
    total_fat_g: float = 0.0
    total_carbs_g: float = 0.0
