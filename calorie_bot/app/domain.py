from dataclasses import dataclass
from datetime import date
from enum import IntEnum, StrEnum


class Sex(StrEnum):
    """Biological sex used for BMR estimation."""

    FEMALE = "female"
    MALE = "male"


class FitnessGoal(StrEnum):
    """Supported nutrition goals for the MVP."""

    LOSE_WEIGHT = "lose_weight"
    MAINTAIN_WEIGHT = "maintain_weight"
    GAIN_WEIGHT = "gain_weight"
    TRACK_CALORIES = "track_calories"


class ActivityLevel(StrEnum):
    """Activity multipliers used for TDEE estimation."""

    SEDENTARY = "sedentary"
    LIGHT = "light"
    MODERATE = "moderate"
    ACTIVE = "active"
    VERY_ACTIVE = "very_active"


class MealStatus(StrEnum):
    """Lifecycle states for a meal."""

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class MealSource(StrEnum):
    """Supported sources for creating or changing meals."""

    PHOTO = "photo"
    TEXT = "text"
    AUDIO = "audio"
    MIXED = "mixed"
    MANUAL = "manual"


class MealType(StrEnum):
    """Supported meal types for user-facing meal grouping."""

    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class AIRequestType(StrEnum):
    """External AI request types tracked for usage and cost control."""

    VISION = "vision"
    SPEECH_TO_TEXT = "speech_to_text"
    CORRECTION = "correction"


class AIRequestStatus(StrEnum):
    """Status values for external AI calls."""

    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class MeasurementUnit(StrEnum):
    """User preference for weight / portion display (MVP: stored for future UI)."""

    METRIC = "metric"
    IMPERIAL = "imperial"


class StatsPeriod(StrEnum):
    """Supported statistics periods."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class TrendWindowDays(IntEnum):
    """Rolling trend lengths (calendar days, inclusive of today)."""

    WEEK = 7
    TWO_WEEKS = 14
    MONTH_ROLLING = 30


class MotivationEventType(StrEnum):
    """Motivation triggers persisted for deduplication and analytics."""

    FIRST_SAVED_MEAL = "first_saved_meal"
    STREAK_3_DAYS = "streak_3_days"
    STREAK_7_DAYS = "streak_7_days"
    CLOSE_TO_GOAL = "close_to_goal"
    RETURNED_AFTER_BREAK = "returned_after_break"
    PHOTO_ENTHUSIAST = "photo_enthusiast"
    REGULARITY_IMPROVED = "regularity_improved"


@dataclass(frozen=True)
class GoalInput:
    """User inputs required to estimate calorie and macro targets."""

    sex: Sex
    age: int
    height_cm: float
    weight_kg: float
    activity_level: ActivityLevel
    goal: FitnessGoal


@dataclass(frozen=True)
class NutritionTargets:
    """Daily calorie and macronutrient targets."""

    bmr_calories: int
    tdee_calories: int
    daily_calorie_target: int
    daily_protein_target_g: int
    daily_fat_target_g: int
    daily_carbs_target_g: int


@dataclass(frozen=True)
class MealItemDraft:
    """Food item draft produced by AI or user correction."""

    name: str
    calories: int
    portion_text: str | None = None
    grams: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbs_g: float | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class MealDraft:
    """Meal draft shown to the user before confirmation."""

    items: list[MealItemDraft]
    total_calories: int
    source: MealSource
    meal_type: MealType | None = None
    confidence: float | None = None
    notes: str | None = None


@dataclass(frozen=True)
class StatsTodayView:
    """Nutrition snapshot for the current calendar day."""

    total_calories: int
    calorie_target: int | None
    remaining_kcal: int | None
    progress_percent: float | None
    meals_count: int
    food_sections: list[str]


@dataclass(frozen=True)
class StatsWeekView:
    """Weekly nutrition summary in the user's timezone."""

    avg_calories_per_day: float | None
    days_above_target: int
    days_below_or_equal_target: int
    days_with_logs: int
    calendar_days_in_window: int
    best_day_label: str | None
    best_day_calories: int | None
    best_day_delta_from_target: int | None
    calorie_target: int | None


@dataclass(frozen=True)
class StatsMonthView:
    """Monthly nutrition summary and simple trend hints."""

    avg_calories_per_day: float | None
    trend_label: str
    days_with_data: int
    days_elapsed_in_month: int
    regularity_percent: float | None
    calorie_target: int | None


@dataclass(frozen=True)
class CalorieTrendPoint:
    """One calendar day for analytics (goal deviation + optional moving average)."""

    day: date
    calories: int
    calorie_goal: int | None
    deviation: int | None
    moving_avg_calories: float | None = None


@dataclass(frozen=True)
class TrendDayPoint:
    """One calendar day in a rolling calorie trend (oldest-first ordering)."""

    day_label: str
    calories: int


@dataclass(frozen=True)
class TrendProductFreq:
    """How often a normalized product appeared in the window."""

    display_name: str
    times_seen: int


@dataclass(frozen=True)
class TrendSourceSlice:
    """Meal input source share inside the window."""

    source_key: str
    display_label: str
    meal_count: int
    percent: float


@dataclass(frozen=True)
class TrendReport:
    """Rolling-window nutrition trend for user-facing summaries."""

    window_days: int
    calorie_target: int | None
    fitness_goal_key: str | None
    daily_points: tuple[TrendDayPoint, ...]
    avg_calories_per_calendar_day: float
    previous_window_avg: float | None
    avg_change_vs_prev_percent: float | None
    days_with_logs: int
    days_without_logs: int
    empty_day_labels: tuple[str, ...]
    regularity_percent: float
    goal_relaxed_match_days: int
    top_products: tuple[TrendProductFreq, ...]
    source_slices: tuple[TrendSourceSlice, ...]
    interpretation_lines: tuple[str, ...]
