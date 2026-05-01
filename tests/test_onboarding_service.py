from types import SimpleNamespace

import pytest

from calorie_bot.app.domain import FitnessGoal
from calorie_bot.app.services.goal_service import GoalService
from calorie_bot.app.services.onboarding_service import OnboardingService


class FakeProfileRepository:
    """Fake profile repository for onboarding service tests."""

    def __init__(self) -> None:
        self.saved = None

    async def upsert_partial_profile(self, **kwargs):
        """Store partial profile kwargs."""
        self.saved = kwargs
        return SimpleNamespace(**kwargs)

    async def upsert_targets(self, user_id, goal_input, targets, timezone, goal_pace="moderate"):
        """Store calculated target kwargs."""
        self.saved = {
            "user_id": user_id,
            "goal": goal_input.goal,
            "daily_calorie_target": targets.daily_calorie_target,
            "timezone": timezone,
        }
        return SimpleNamespace(**self.saved)


class FakeWeightLogRepository:
    """Fake weight log repository for onboarding service tests."""

    def __init__(self) -> None:
        self.logs = []

    async def add_weight(self, user_id, weight_kg, logged_at):
        """Store weight log args."""
        self.logs.append((user_id, weight_kg, logged_at))


class FakeSettingsRepository:
    """Fake settings repository for onboarding service tests."""

    def __init__(self) -> None:
        self.saved = []

    async def upsert_settings(self, user_id, timezone="Europe/Moscow", **kwargs):
        """Store settings args."""
        self.saved.append((user_id, timezone, kwargs))


@pytest.mark.asyncio
async def test_manual_calorie_onboarding_completes_user() -> None:
    """Manual calorie target should complete onboarding without anthropometrics."""
    user = SimpleNamespace(id=1, onboarding_completed=False, onboarding_status="not_started")
    profile_repo = FakeProfileRepository()
    service = OnboardingService(
        profile_repository=profile_repo,
        weight_log_repository=FakeWeightLogRepository(),
        settings_repository=FakeSettingsRepository(),
        goal_service=GoalService(),
    )

    await service.complete_with_manual_calories(
        user=user,
        goal=FitnessGoal.TRACK_CALORIES,
        daily_calorie_target=1800,
        timezone="Europe/Moscow",
    )

    assert user.onboarding_completed is True
    assert user.onboarding_status == "completed"
    assert profile_repo.saved["daily_calorie_target"] == 1800
    assert profile_repo.saved["goal"] == FitnessGoal.TRACK_CALORIES


@pytest.mark.asyncio
async def test_partial_onboarding_completes_without_calculation() -> None:
    """Skipped calculation data should still save the selected goal."""
    user = SimpleNamespace(id=2, onboarding_completed=False, onboarding_status="not_started")
    profile_repo = FakeProfileRepository()
    weight_repo = FakeWeightLogRepository()
    service = OnboardingService(
        profile_repository=profile_repo,
        weight_log_repository=weight_repo,
        settings_repository=FakeSettingsRepository(),
        goal_service=GoalService(),
    )

    await service.complete_with_partial_data(
        user=user,
        data={"goal": FitnessGoal.MAINTAIN_WEIGHT.value, "weight_kg": None},
        timezone="Europe/Moscow",
    )

    assert user.onboarding_completed is True
    assert profile_repo.saved["goal"] == FitnessGoal.MAINTAIN_WEIGHT
    assert weight_repo.logs == []
