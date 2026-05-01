"""Tests for ``UserSettingsService`` orchestration and guards."""

from types import SimpleNamespace

import pytest

from calorie_bot.app.domain import MeasurementUnit
from calorie_bot.app.services.goal_service import GoalService
from calorie_bot.app.services.user_settings_service import UserSettingsService


class FakeSettingsRepository:
    """In-memory app settings row."""

    def __init__(self) -> None:
        self.row: SimpleNamespace | None = None
        self.ai_flag = True

    async def get_by_user_id(self, user_id: int) -> SimpleNamespace | None:
        return self.row

    async def get_or_create(self, user_id: int) -> SimpleNamespace:
        if self.row is None:
            self.row = SimpleNamespace(
                user_id=user_id,
                notifications_enabled=True,
                motivation_messages_enabled=True,
                ai_analysis_enabled=self.ai_flag,
                measurement_unit="metric",
            )
        return self.row

    async def set_notifications_enabled(self, user_id: int, enabled: bool) -> SimpleNamespace:
        row = await self.get_or_create(user_id)
        row.notifications_enabled = enabled
        return row

    async def set_motivation_messages_enabled(self, user_id: int, enabled: bool) -> SimpleNamespace:
        row = await self.get_or_create(user_id)
        row.motivation_messages_enabled = enabled
        return row

    async def set_ai_analysis_enabled(self, user_id: int, enabled: bool) -> SimpleNamespace:
        row = await self.get_or_create(user_id)
        row.ai_analysis_enabled = enabled
        return row

    async def set_measurement_unit(self, user_id: int, unit_key: str) -> SimpleNamespace:
        row = await self.get_or_create(user_id)
        row.measurement_unit = unit_key
        return row

    async def update_timezone(self, user_id: int, timezone: str) -> SimpleNamespace:
        row = await self.get_or_create(user_id)
        row.timezone = timezone
        return row


class FakeProfileRepository:
    """Minimal profile with timezone for target sync tests."""

    def __init__(self) -> None:
        self.profile = SimpleNamespace(
            user_id=1,
            goal="track_calories",
            sex="male",
            age=30,
            height_cm=180.0,
            weight_kg=80.0,
            activity_level="moderate",
            timezone="Europe/Moscow",
            daily_calorie_target=2000,
            daily_protein_target_g=100,
            daily_fat_target_g=60,
            daily_carbs_target_g=200,
        )
        self.updated_calories: int | None = None
        self.timezone_updates: list[str] = []

    async def get_by_user_id(self, user_id: int) -> SimpleNamespace | None:
        return self.profile

    async def update_daily_calorie_target(self, user_id: int, calories: int) -> SimpleNamespace:
        self.updated_calories = calories
        self.profile.daily_calorie_target = calories
        return self.profile

    async def update_timezone_only(self, user_id: int, timezone: str) -> SimpleNamespace:
        self.timezone_updates.append(timezone)
        self.profile.timezone = timezone
        return self.profile

    async def build_goal_input(self, profile: SimpleNamespace):
        from calorie_bot.app.domain import ActivityLevel, FitnessGoal, GoalInput, Sex

        return GoalInput(
            sex=Sex(str(profile.sex)),
            age=int(profile.age),
            height_cm=float(profile.height_cm),
            weight_kg=float(profile.weight_kg),
            activity_level=ActivityLevel(str(profile.activity_level)),
            goal=FitnessGoal(str(profile.goal)),
        )

    async def upsert_targets(self, user_id, goal_input, targets, timezone, goal_pace="moderate"):
        self.profile.daily_calorie_target = targets.daily_calorie_target
        self.profile.daily_protein_target_g = targets.daily_protein_target_g
        self.profile.daily_fat_target_g = targets.daily_fat_target_g
        self.profile.daily_carbs_target_g = targets.daily_carbs_target_g
        return self.profile


class FakeDailyStatsRepository:
    def __init__(self) -> None:
        self.sync_calls: list[int] = []

    async def sync_targets_from_profile(self, user_id: int, profile) -> None:
        self.sync_calls.append(user_id)


class FakePurgeRepository:
    def __init__(self) -> None:
        self.purged: list[int] = []

    async def purge_user_data(self, user_id: int) -> None:
        self.purged.append(user_id)


@pytest.mark.asyncio
async def test_ai_disabled_when_row_opted_out() -> None:
    """Respect stored opt-out for external AI."""
    settings_repo = FakeSettingsRepository()
    settings_repo.row = SimpleNamespace(ai_analysis_enabled=False)
    service = UserSettingsService(
        settings_repository=settings_repo,
        profile_repository=FakeProfileRepository(),
        daily_stats_repository=FakeDailyStatsRepository(),
        purge_repository=FakePurgeRepository(),
        goal_service=GoalService(),
    )
    assert await service.is_ai_analysis_enabled(1) is False


@pytest.mark.asyncio
async def test_ai_enabled_when_no_settings_row() -> None:
    """Default allows AI before first settings insert."""
    service = UserSettingsService(
        settings_repository=FakeSettingsRepository(),
        profile_repository=FakeProfileRepository(),
        daily_stats_repository=FakeDailyStatsRepository(),
        purge_repository=FakePurgeRepository(),
        goal_service=GoalService(),
    )
    assert await service.is_ai_analysis_enabled(42) is True


@pytest.mark.asyncio
async def test_calorie_goal_updates_syncs_daily_stats() -> None:
    """Changing kcal should refresh denormalized progress anchors."""
    daily = FakeDailyStatsRepository()
    service = UserSettingsService(
        settings_repository=FakeSettingsRepository(),
        profile_repository=FakeProfileRepository(),
        daily_stats_repository=daily,
        purge_repository=FakePurgeRepository(),
        goal_service=GoalService(),
    )
    await service.set_daily_calorie_target(1, 1900)
    assert daily.sync_calls == [1]


@pytest.mark.asyncio
async def test_timezone_update_validates_and_syncs() -> None:
    daily = FakeDailyStatsRepository()
    profiles = FakeProfileRepository()
    service = UserSettingsService(
        settings_repository=FakeSettingsRepository(),
        profile_repository=profiles,
        daily_stats_repository=daily,
        purge_repository=FakePurgeRepository(),
        goal_service=GoalService(),
    )
    await service.update_timezone(1, "Europe/Berlin")
    assert profiles.timezone_updates == ["Europe/Berlin"]
    assert daily.sync_calls == [1]


@pytest.mark.asyncio
async def test_invalid_timezone_raises() -> None:
    service = UserSettingsService(
        settings_repository=FakeSettingsRepository(),
        profile_repository=FakeProfileRepository(),
        daily_stats_repository=FakeDailyStatsRepository(),
        purge_repository=FakePurgeRepository(),
        goal_service=GoalService(),
    )
    with pytest.raises(ValueError, match="invalid_timezone"):
        await service.update_timezone(1, "Not/A/Zone")


@pytest.mark.asyncio
async def test_measurement_unit_persisted() -> None:
    repo = FakeSettingsRepository()
    service = UserSettingsService(
        settings_repository=repo,
        profile_repository=FakeProfileRepository(),
        daily_stats_repository=FakeDailyStatsRepository(),
        purge_repository=FakePurgeRepository(),
        goal_service=GoalService(),
    )
    await service.set_measurement_unit(1, MeasurementUnit.IMPERIAL)
    row = await repo.get_or_create(1)
    assert row.measurement_unit == "imperial"


@pytest.mark.asyncio
async def test_recalculate_targets_returns_false_without_full_inputs() -> None:
    class PartialProfileRepo(FakeProfileRepository):
        async def build_goal_input(self, profile):
            raise ValueError("incomplete")

    service = UserSettingsService(
        settings_repository=FakeSettingsRepository(),
        profile_repository=PartialProfileRepo(),
        daily_stats_repository=FakeDailyStatsRepository(),
        purge_repository=FakePurgeRepository(),
        goal_service=GoalService(),
    )
    assert await service.recalculate_targets_from_profile(1) is False


@pytest.mark.asyncio
async def test_purge_delegates_to_repository() -> None:
    purge = FakePurgeRepository()
    service = UserSettingsService(
        settings_repository=FakeSettingsRepository(),
        profile_repository=FakeProfileRepository(),
        daily_stats_repository=FakeDailyStatsRepository(),
        purge_repository=purge,
        goal_service=GoalService(),
    )
    await service.purge_all_data(7)
    assert purge.purged == [7]
