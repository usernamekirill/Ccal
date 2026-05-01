"""Tests for denormalized daily_stats sync helpers."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from calorie_bot.app.config import Settings
from calorie_bot.app.domain import MealStatus
from calorie_bot.app.services import daily_stats_sync


@pytest.fixture
def settings() -> Settings:
    """Minimal settings for sync tests."""
    return Settings()


@pytest.mark.asyncio
async def test_on_confirmed_meal_edited_subtracts_then_adds(settings: Settings) -> None:
    """Editing a confirmed meal should adjust rollups without changing meal count net."""
    subtract = AsyncMock()
    add = AsyncMock()
    profile = SimpleNamespace(timezone="UTC", daily_calorie_target=2000)
    prof = SimpleNamespace(get_by_user_id=AsyncMock(return_value=profile))

    with (
        patch.object(daily_stats_sync, "DailyStatsRepository") as stats_repo_cls,
        patch.object(daily_stats_sync, "ProfileRepository", return_value=prof),
    ):
        repo_inst = SimpleNamespace(
            subtract_confirmed_meal_totals=subtract,
            add_confirmed_meal_totals=add,
        )
        stats_repo_cls.return_value = repo_inst

        after = SimpleNamespace(
            eaten_at=datetime(2026, 4, 30, 15, tzinfo=UTC),
            status=MealStatus.CONFIRMED.value,
            total_calories=180,
            total_protein_g=10.0,
            total_fat_g=5.0,
            total_carbs_g=20.0,
        )
        session = AsyncMock()
        await daily_stats_sync.on_confirmed_meal_edited(
            session,
            settings,
            user_sql_id=1,
            before_eaten_at=datetime(2026, 4, 30, 12, tzinfo=UTC),
            before_calories=300,
            before_protein_g=20.0,
            before_fat_g=10.0,
            before_carbs_g=30.0,
            before_status=MealStatus.CONFIRMED.value,
            after_meal=after,
        )

    subtract.assert_awaited_once()
    add.assert_awaited_once()
    kw_sub = subtract.await_args.kwargs
    assert kw_sub["calories"] == 300
    kw_add = add.await_args.kwargs
    assert kw_add["calories"] == 180


@pytest.mark.asyncio
async def test_on_confirmed_meal_edited_skips_when_before_not_confirmed(
    settings: Settings,
) -> None:
    """Non-confirmed before state should not touch daily_stats."""
    subtract = AsyncMock()
    add = AsyncMock()
    prof = SimpleNamespace(get_by_user_id=AsyncMock(return_value=None))

    with (
        patch.object(daily_stats_sync, "DailyStatsRepository") as stats_repo_cls,
        patch.object(daily_stats_sync, "ProfileRepository", return_value=prof),
    ):
        stats_repo_cls.return_value = SimpleNamespace(
            subtract_confirmed_meal_totals=subtract,
            add_confirmed_meal_totals=add,
        )
        after = SimpleNamespace(
            eaten_at=datetime(2026, 4, 30, tzinfo=UTC),
            status=MealStatus.CONFIRMED.value,
            total_calories=100,
            total_protein_g=0.0,
            total_fat_g=0.0,
            total_carbs_g=0.0,
        )
        await daily_stats_sync.on_confirmed_meal_edited(
            AsyncMock(),
            settings,
            user_sql_id=1,
            before_eaten_at=after.eaten_at,
            before_calories=50,
            before_protein_g=0.0,
            before_fat_g=0.0,
            before_carbs_g=0.0,
            before_status=MealStatus.DRAFT.value,
            after_meal=after,
        )

    subtract.assert_not_awaited()
    add.assert_not_awaited()
