from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.database.models import UserProfile, WeightLog
from calorie_bot.app.domain import ActivityLevel, FitnessGoal, GoalInput, NutritionTargets, Sex


class ProfileRepository:
    """Persist user nutrition profile and targets."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: int) -> UserProfile | None:
        """Return a user's nutrition profile."""
        result = await self._session.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert_targets(
        self,
        user_id: int,
        goal_input: GoalInput,
        targets: NutritionTargets,
        timezone: str,
        goal_pace: str = "moderate",
    ) -> UserProfile:
        """Create or update a user profile with calculated nutrition targets."""
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)
            self._session.add(profile)

        profile.goal = goal_input.goal.value
        profile.sex = goal_input.sex.value
        profile.age = goal_input.age
        profile.height_cm = goal_input.height_cm
        profile.weight_kg = goal_input.weight_kg
        profile.activity_level = goal_input.activity_level.value
        profile.goal_pace = goal_pace
        profile.bmr_calories = targets.bmr_calories
        profile.tdee_calories = targets.tdee_calories
        profile.daily_calorie_target = targets.daily_calorie_target
        profile.daily_protein_target_g = targets.daily_protein_target_g
        profile.daily_fat_target_g = targets.daily_fat_target_g
        profile.daily_carbs_target_g = targets.daily_carbs_target_g
        profile.timezone = timezone
        return profile

    async def upsert_partial_profile(
        self,
        user_id: int,
        goal: FitnessGoal,
        timezone: str,
        daily_calorie_target: int | None = None,
        sex: Sex | None = None,
        age: int | None = None,
        height_cm: float | None = None,
        weight_kg: float | None = None,
        activity_level: ActivityLevel | None = None,
    ) -> UserProfile:
        """Create or update a profile when the user skips some onboarding answers."""
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)
            self._session.add(profile)

        profile.goal = goal.value
        profile.sex = sex.value if sex else None
        profile.age = age
        profile.height_cm = height_cm
        profile.weight_kg = weight_kg
        profile.activity_level = activity_level.value if activity_level else None
        profile.daily_calorie_target = daily_calorie_target
        profile.daily_protein_target_g = None
        profile.daily_fat_target_g = None
        profile.daily_carbs_target_g = None
        profile.bmr_calories = None
        profile.tdee_calories = None
        profile.timezone = timezone
        return profile

    async def build_goal_input(self, profile: UserProfile) -> GoalInput:
        """Return goal input reconstructed from a persisted profile."""
        if not all(
            [
                profile.sex,
                profile.age,
                profile.height_cm,
                profile.weight_kg,
                profile.activity_level,
                profile.goal,
            ]
        ):
            raise ValueError("Profile does not contain enough data for target calculation.")
        return GoalInput(
            sex=Sex(profile.sex),
            age=profile.age,
            height_cm=profile.height_cm,
            weight_kg=profile.weight_kg,
            activity_level=ActivityLevel(profile.activity_level),
            goal=FitnessGoal(profile.goal),
        )

    async def update_daily_calorie_target(self, user_id: int, calories: int) -> UserProfile:
        """Update only the daily calorie target (macros unchanged)."""
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            raise ValueError("profile_not_found")
        profile.daily_calorie_target = calories
        await self._session.flush()
        return profile

    async def update_timezone_only(self, user_id: int, timezone: str) -> UserProfile:
        """Update stored timezone on the nutrition profile."""
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            raise ValueError("profile_not_found")
        profile.timezone = timezone
        await self._session.flush()
        return profile


class WeightLogRepository:
    """Persist user weight history."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_weight(self, user_id: int, weight_kg: float, logged_at: datetime) -> WeightLog:
        """Add a user weight log entry."""
        log = WeightLog(user_id=user_id, weight_kg=weight_kg, logged_at=logged_at)
        self._session.add(log)
        return log
