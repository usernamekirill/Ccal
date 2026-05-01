"""Coordinated user preferences, nutrition target edits, and data removal."""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.domain import MeasurementUnit
from calorie_bot.app.repositories.daily_stats_repository import DailyStatsRepository
from calorie_bot.app.repositories.profile_repository import ProfileRepository
from calorie_bot.app.repositories.settings_repository import SettingsRepository
from calorie_bot.app.repositories.user_purge_repository import UserPurgeRepository
from calorie_bot.app.services.goal_service import GoalService

logger = logging.getLogger(__name__)

_CALORIE_MIN = 500
_CALORIE_MAX = 8000


class UserSettingsService:
    """Apply settings changes with logging and progress denormalization updates."""

    def __init__(
        self,
        *,
        settings_repository: SettingsRepository,
        profile_repository: ProfileRepository,
        daily_stats_repository: DailyStatsRepository,
        purge_repository: UserPurgeRepository,
        goal_service: GoalService,
    ) -> None:
        self._settings_repository = settings_repository
        self._profile_repository = profile_repository
        self._daily_stats_repository = daily_stats_repository
        self._purge_repository = purge_repository
        self._goal_service = goal_service

    async def is_ai_analysis_enabled(self, user_id: int) -> bool:
        """Return False when the user opted out of external AI (vision, speech, LLM)."""
        row = await self._settings_repository.get_by_user_id(user_id)
        if row is None:
            return True
        return bool(row.ai_analysis_enabled)

    async def update_timezone(self, user_id: int, timezone_name: str) -> None:
        """Validate IANA timezone and mirror it on profile + app settings."""
        self._validate_timezone(timezone_name)
        await self._profile_repository.update_timezone_only(user_id, timezone_name)
        await self._settings_repository.update_timezone(user_id, timezone_name)
        profile = await self._profile_repository.get_by_user_id(user_id)
        if profile is not None:
            await self._daily_stats_repository.sync_targets_from_profile(user_id, profile)
        logger.info(
            "settings_updated action=timezone internal_user_id=%s",
            user_id,
        )

    async def set_daily_calorie_target(self, user_id: int, calories: int) -> None:
        """Persist a new calorie target and refresh denormalized progress rows."""
        if calories < _CALORIE_MIN or calories > _CALORIE_MAX:
            raise ValueError("calorie_target_out_of_range")
        profile = await self._profile_repository.update_daily_calorie_target(user_id, calories)
        await self._daily_stats_repository.sync_targets_from_profile(user_id, profile)
        logger.info(
            "settings_updated action=calorie_goal internal_user_id=%s",
            user_id,
        )

    async def recalculate_targets_from_profile(self, user_id: int) -> bool:
        """Recompute TDEE/macros when anthropometrics are complete; sync daily progress rows."""
        profile = await self._profile_repository.get_by_user_id(user_id)
        if profile is None:
            return False
        try:
            goal_input = await self._profile_repository.build_goal_input(profile)
        except ValueError:
            return False
        targets = self._goal_service.calculate_daily_targets(goal_input)
        await self._profile_repository.upsert_targets(
            user_id=user_id,
            goal_input=goal_input,
            targets=targets,
            timezone=profile.timezone,
        )
        updated = await self._profile_repository.get_by_user_id(user_id)
        if updated is None:
            return False
        await self._daily_stats_repository.sync_targets_from_profile(user_id, updated)
        logger.info("settings_updated action=targets_recalc internal_user_id=%s", user_id)
        return True

    async def set_notifications_enabled(self, user_id: int, enabled: bool) -> None:
        """Store notification channel preference (MVP: no outbound scheduler yet)."""
        await self._settings_repository.set_notifications_enabled(user_id, enabled)
        logger.info(
            "settings_updated action=notifications internal_user_id=%s value=%s",
            user_id,
            enabled,
        )

    async def set_motivation_enabled(self, user_id: int, enabled: bool) -> None:
        """Toggle motivational copy after meals and in stats."""
        await self._settings_repository.set_motivation_messages_enabled(user_id, enabled)
        logger.info(
            "settings_updated action=motivation internal_user_id=%s value=%s",
            user_id,
            enabled,
        )

    async def set_ai_analysis_enabled(self, user_id: int, enabled: bool) -> None:
        """Toggle permission for OpenAI-backed features."""
        await self._settings_repository.set_ai_analysis_enabled(user_id, enabled)
        logger.info(
            "settings_updated action=ai_analysis internal_user_id=%s value=%s",
            user_id,
            enabled,
        )

    async def set_measurement_unit(self, user_id: int, unit: MeasurementUnit) -> None:
        """Persist measurement unit preference."""
        await self._settings_repository.set_measurement_unit(user_id, unit.value)
        logger.info(
            "settings_updated action=units internal_user_id=%s value=%s",
            user_id,
            unit.value,
        )

    async def purge_all_data(self, user_id: int) -> None:
        """Hard-delete all rows for this internal user id."""
        await self._purge_repository.purge_user_data(user_id)
        logger.info("user_data_purged internal_user_id=%s", user_id)

    @staticmethod
    def _validate_timezone(name: str) -> None:
        try:
            ZoneInfo(name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("invalid_timezone") from exc


def create_user_settings_service(
    session: AsyncSession,
    goal_service: GoalService,
) -> UserSettingsService:
    """Factory wiring repositories for handlers."""
    return UserSettingsService(
        settings_repository=SettingsRepository(session),
        profile_repository=ProfileRepository(session),
        daily_stats_repository=DailyStatsRepository(session),
        purge_repository=UserPurgeRepository(session),
        goal_service=goal_service,
    )
