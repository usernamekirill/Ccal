from datetime import datetime
from zoneinfo import ZoneInfo

from calorie_bot.app.database.models import User, UserProfile
from calorie_bot.app.domain import ActivityLevel, FitnessGoal, GoalInput, NutritionTargets, Sex
from calorie_bot.app.repositories.profile_repository import ProfileRepository, WeightLogRepository
from calorie_bot.app.repositories.settings_repository import SettingsRepository
from calorie_bot.app.services.goal_service import GoalService


class OnboardingService:
    """Complete onboarding and persist user nutrition targets."""

    def __init__(
        self,
        profile_repository: ProfileRepository,
        weight_log_repository: WeightLogRepository,
        settings_repository: SettingsRepository,
        goal_service: GoalService,
    ) -> None:
        self._profile_repository = profile_repository
        self._weight_log_repository = weight_log_repository
        self._settings_repository = settings_repository
        self._goal_service = goal_service

    async def complete_onboarding(
        self,
        user: User,
        goal_input: GoalInput,
        timezone: str,
    ) -> tuple[UserProfile, NutritionTargets]:
        """Calculate and save nutrition targets for a user."""
        targets = self._goal_service.calculate_daily_targets(goal_input)
        profile = await self._profile_repository.upsert_targets(
            user_id=user.id,
            goal_input=goal_input,
            targets=targets,
            timezone=timezone,
        )
        await self._weight_log_repository.add_weight(
            user_id=user.id,
            weight_kg=goal_input.weight_kg,
            logged_at=datetime.now(ZoneInfo(timezone)),
        )
        await self._settings_repository.upsert_settings(user_id=user.id, timezone=timezone)
        self.mark_completed(user)
        return profile, targets

    async def complete_with_manual_calories(
        self,
        user: User,
        goal: FitnessGoal,
        daily_calorie_target: int | None,
        timezone: str,
    ) -> UserProfile:
        """Complete onboarding with a manually entered or skipped calorie goal."""
        profile = await self._profile_repository.upsert_partial_profile(
            user_id=user.id,
            goal=goal,
            daily_calorie_target=daily_calorie_target,
            timezone=timezone,
        )
        await self._settings_repository.upsert_settings(user_id=user.id, timezone=timezone)
        self.mark_completed(user)
        return profile

    async def complete_with_partial_data(
        self,
        user: User,
        data: dict[str, object],
        timezone: str,
    ) -> UserProfile:
        """Complete onboarding after skipped calculation questions."""
        profile = await self._profile_repository.upsert_partial_profile(
            user_id=user.id,
            goal=FitnessGoal(str(data["goal"])),
            timezone=timezone,
            sex=_optional_enum(data, "sex", Sex),
            age=_optional_int(data, "age"),
            height_cm=_optional_float(data, "height_cm"),
            weight_kg=_optional_float(data, "weight_kg"),
            activity_level=_optional_enum(data, "activity_level", ActivityLevel),
        )
        await self._settings_repository.upsert_settings(user_id=user.id, timezone=timezone)
        if profile.weight_kg is not None:
            await self._weight_log_repository.add_weight(
                user_id=user.id,
                weight_kg=profile.weight_kg,
                logged_at=datetime.now(ZoneInfo(timezone)),
            )
        self.mark_completed(user)
        return profile

    def can_calculate_targets(self, data: dict[str, object]) -> bool:
        """Return whether FSM data contains all fields needed for calculation."""
        required = ("goal", "sex", "age", "height_cm", "weight_kg", "activity_level")
        return all(data.get(key) is not None for key in required)

    def mark_completed(self, user: User) -> None:
        """Mark onboarding as completed on the user model."""
        user.onboarding_completed = True
        user.onboarding_status = "completed"


def build_goal_input_from_fsm(data: dict[str, object]) -> GoalInput:
    """Build validated goal input from aiogram FSM data."""
    return GoalInput(
        sex=Sex(str(data["sex"])),
        age=int(data["age"]),
        height_cm=float(data["height_cm"]),
        weight_kg=float(data["weight_kg"]),
        activity_level=ActivityLevel(str(data["activity_level"])),
        goal=FitnessGoal(str(data["goal"])),
    )


def _optional_int(data: dict[str, object], key: str) -> int | None:
    value = data.get(key)
    return int(value) if value is not None else None


def _optional_float(data: dict[str, object], key: str) -> float | None:
    value = data.get(key)
    return float(value) if value is not None else None


def _optional_enum(data: dict[str, object], key: str, enum_type):
    value = data.get(key)
    return enum_type(str(value)) if value is not None else None
