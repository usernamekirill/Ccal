from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from calorie_bot.app.database.base import Base


class TimestampMixin:
    """Common created and updated timestamps for database models."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class SoftDeleteMixin:
    """Soft deletion timestamp for user-owned data."""

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class User(TimestampMixin, SoftDeleteMixin, Base):
    """Telegram user known by the bot."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    onboarding_completed: Mapped[bool] = mapped_column(default=False)
    onboarding_status: Mapped[str] = mapped_column(String(32), default="not_started")

    profile: Mapped["UserProfile | None"] = relationship(back_populates="user")
    settings: Mapped["UserSettings | None"] = relationship(back_populates="user")
    meals: Mapped[list["Meal"]] = relationship(back_populates="user")


class UserProfile(TimestampMixin, Base):
    """Nutrition profile and targets for a user."""

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    goal: Mapped[str | None] = mapped_column(String(32))
    sex: Mapped[str | None] = mapped_column(String(16))
    age: Mapped[int | None] = mapped_column(Integer)
    height_cm: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    activity_level: Mapped[str | None] = mapped_column(String(32))
    goal_pace: Mapped[str] = mapped_column(String(32), default="moderate")
    bmr_calories: Mapped[int | None] = mapped_column(Integer)
    tdee_calories: Mapped[int | None] = mapped_column(Integer)
    daily_calorie_target: Mapped[int | None] = mapped_column(Integer)
    daily_protein_target_g: Mapped[int | None] = mapped_column(Integer)
    daily_fat_target_g: Mapped[int | None] = mapped_column(Integer)
    daily_carbs_target_g: Mapped[int | None] = mapped_column(Integer)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")

    user: Mapped["User"] = relationship(back_populates="profile")


class UserSettings(TimestampMixin, Base):
    """User-configurable app settings that do not include secrets."""

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    language: Mapped[str] = mapped_column(String(16), default="ru")
    tone: Mapped[str] = mapped_column(String(32), default="friendly")
    ai_daily_soft_limit: Mapped[int] = mapped_column(Integer, default=50)
    data_retention_days: Mapped[int | None] = mapped_column(Integer)
    motivation_messages_enabled: Mapped[bool] = mapped_column(default=True)
    notifications_enabled: Mapped[bool] = mapped_column(default=True)
    ai_analysis_enabled: Mapped[bool] = mapped_column(default=True)
    measurement_unit: Mapped[str] = mapped_column(String(16), default="metric")

    user: Mapped["User"] = relationship(back_populates="settings")


class Meal(TimestampMixin, SoftDeleteMixin, Base):
    """Meal draft or confirmed meal logged by a user."""

    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    source: Mapped[str] = mapped_column(String(32))
    meal_type: Mapped[str | None] = mapped_column(String(32))
    eaten_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    total_calories: Mapped[int] = mapped_column(Integer, default=0)
    total_calories_min: Mapped[int | None] = mapped_column(Integer)
    total_calories_max: Mapped[int | None] = mapped_column(Integer)
    has_estimated_items: Mapped[bool] = mapped_column(default=False)
    total_protein_g: Mapped[float | None] = mapped_column(Float)
    total_fat_g: Mapped[float | None] = mapped_column(Float)
    total_carbs_g: Mapped[float | None] = mapped_column(Float)
    ai_confidence: Mapped[float | None] = mapped_column(Float)

    user: Mapped["User"] = relationship(back_populates="meals")
    items: Mapped[list["MealItem"]] = relationship(back_populates="meal")

    __table_args__ = (
        Index("ix_meals_user_eaten_at", "user_id", "eaten_at"),
        Index("ix_meals_user_status", "user_id", "status"),
    )


class MealItem(TimestampMixin, Base):
    """Food item inside a meal."""

    __tablename__ = "meal_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    meal_id: Mapped[int] = mapped_column(ForeignKey("meals.id"), index=True)
    ai_result_id: Mapped[int | None] = mapped_column(ForeignKey("meal_ai_results.id"))
    name: Mapped[str] = mapped_column(String(255))
    portion_text: Mapped[str | None] = mapped_column(String(255))
    grams: Mapped[float | None] = mapped_column(Float)
    grams_min: Mapped[float | None] = mapped_column(Float)
    grams_max: Mapped[float | None] = mapped_column(Float)
    grams_source: Mapped[str | None] = mapped_column(String(32))
    calories: Mapped[int | None] = mapped_column(Integer)
    calories_min: Mapped[int | None] = mapped_column(Integer)
    calories_max: Mapped[int | None] = mapped_column(Integer)
    calories_per_100g: Mapped[float | None] = mapped_column(Float)
    protein_per_100g: Mapped[float | None] = mapped_column(Float)
    fat_per_100g: Mapped[float | None] = mapped_column(Float)
    carbs_per_100g: Mapped[float | None] = mapped_column(Float)
    protein_g: Mapped[float | None] = mapped_column(Float)
    fat_g: Mapped[float | None] = mapped_column(Float)
    carbs_g: Mapped[float | None] = mapped_column(Float)
    protein_g_min: Mapped[float | None] = mapped_column(Float)
    protein_g_max: Mapped[float | None] = mapped_column(Float)
    fat_g_min: Mapped[float | None] = mapped_column(Float)
    fat_g_max: Mapped[float | None] = mapped_column(Float)
    carbs_g_min: Mapped[float | None] = mapped_column(Float)
    carbs_g_max: Mapped[float | None] = mapped_column(Float)
    food_confidence: Mapped[float | None] = mapped_column(Float)
    portion_confidence: Mapped[float | None] = mapped_column(Float)
    needs_portion_clarification: Mapped[bool] = mapped_column(default=False)
    is_estimated: Mapped[bool] = mapped_column(default=False)
    confidence: Mapped[float | None] = mapped_column(Float)

    meal: Mapped["Meal"] = relationship(back_populates="items")


class FoodCache(TimestampMixin, Base):
    """Cached nutrition estimate for a normalized food name."""

    __tablename__ = "food_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    calories_per_100g: Mapped[float] = mapped_column(Float)
    protein_per_100g: Mapped[float | None] = mapped_column(Float)
    fat_per_100g: Mapped[float | None] = mapped_column(Float)
    carbs_per_100g: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, default=0.7)
    source: Mapped[str] = mapped_column(String(32), default="ai")
    is_estimated: Mapped[bool] = mapped_column(default=True)


class MealAIResult(TimestampMixin, Base):
    """Structured AI recognition result without raw media payloads."""

    __tablename__ = "meal_ai_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    meal_id: Mapped[int | None] = mapped_column(ForeignKey("meals.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    request_type: Mapped[str] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(128))
    confidence: Mapped[float | None] = mapped_column(Float)
    structured_result: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="succeeded")


class MealCorrection(TimestampMixin, Base):
    """User correction applied to a meal draft or confirmed meal."""

    __tablename__ = "meal_corrections"

    id: Mapped[int] = mapped_column(primary_key=True)
    meal_id: Mapped[int] = mapped_column(ForeignKey("meals.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String(32))
    correction_text: Mapped[str | None] = mapped_column(Text)
    before_snapshot: Mapped[dict | None] = mapped_column(JSON)
    after_snapshot: Mapped[dict | None] = mapped_column(JSON)


class MealHistory(TimestampMixin, Base):
    """Audit history for meal changes."""

    __tablename__ = "meal_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    meal_id: Mapped[int] = mapped_column(ForeignKey("meals.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    snapshot: Mapped[dict | None] = mapped_column(JSON)


class MealChangeLog(TimestampMixin, Base):
    """Before/after change log for meal edits and deletions."""

    __tablename__ = "meal_change_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    meal_id: Mapped[int] = mapped_column(ForeignKey("meals.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(32))
    before_snapshot: Mapped[dict | None] = mapped_column(JSON)
    after_snapshot: Mapped[dict | None] = mapped_column(JSON)


class WeightLog(TimestampMixin, Base):
    """Manually logged user weight."""

    __tablename__ = "weight_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    weight_kg: Mapped[float] = mapped_column(Float)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DailyStats(TimestampMixin, Base):
    """Denormalized daily nutrition statistics."""

    __tablename__ = "daily_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    stat_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    total_calories: Mapped[int] = mapped_column(Integer, default=0)
    total_protein_g: Mapped[float] = mapped_column(Float, default=0)
    total_fat_g: Mapped[float] = mapped_column(Float, default=0)
    total_carbs_g: Mapped[float] = mapped_column(Float, default=0)
    meals_count: Mapped[int] = mapped_column(Integer, default=0)
    calorie_target: Mapped[int | None] = mapped_column(Integer)
    protein_target_g: Mapped[int | None] = mapped_column(Integer)
    fat_target_g: Mapped[int | None] = mapped_column(Integer)
    carbs_target_g: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (Index("ix_daily_stats_user_date", "user_id", "stat_date", unique=True),)


class MotivationEvent(TimestampMixin, Base):
    """Motivational event emitted by product logic."""

    __tablename__ = "motivation_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict | None] = mapped_column(JSON)


class ErrorLog(TimestampMixin, Base):
    """Safe technical error log without sensitive request payloads."""

    __tablename__ = "error_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    error_type: Mapped[str] = mapped_column(String(128))
    handler: Mapped[str | None] = mapped_column(String(128))
    safe_message: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)


class AIRequest(TimestampMixin, Base):
    """Metadata for external AI calls without sensitive payloads."""

    __tablename__ = "ai_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    meal_id: Mapped[int | None] = mapped_column(ForeignKey("meals.id"))
    request_type: Mapped[str] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    input_units: Mapped[int | None] = mapped_column(Integer)
    output_units: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)
