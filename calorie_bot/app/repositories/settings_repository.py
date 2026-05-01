from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.database.models import UserSettings


class SettingsRepository:
    """Read and write user-facing settings."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: int) -> UserSettings | None:
        """Return app settings for a user."""
        result = await self._session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert_settings(
        self,
        user_id: int,
        timezone: str = "Europe/Moscow",
        language: str = "ru",
        tone: str = "friendly",
        ai_daily_soft_limit: int = 50,
        data_retention_days: int | None = None,
    ) -> UserSettings:
        """Create or update user-facing settings."""
        settings = await self.get_by_user_id(user_id)
        if settings is None:
            settings = UserSettings(
                user_id=user_id,
                motivation_messages_enabled=True,
                notifications_enabled=True,
                ai_analysis_enabled=True,
                measurement_unit="metric",
            )
            self._session.add(settings)

        settings.timezone = timezone
        settings.language = language
        settings.tone = tone
        settings.ai_daily_soft_limit = ai_daily_soft_limit
        settings.data_retention_days = data_retention_days
        return settings

    async def update_timezone(self, user_id: int, timezone: str) -> UserSettings:
        """Update user timezone."""
        settings = await self.upsert_settings(user_id=user_id)
        settings.timezone = timezone
        return settings

    async def set_motivation_messages_enabled(
        self,
        user_id: int,
        enabled: bool,
    ) -> UserSettings:
        """Toggle motivational nudges after meals and on stats."""
        settings = await self.get_by_user_id(user_id)
        if settings is None:
            settings = UserSettings(
                user_id=user_id,
                motivation_messages_enabled=enabled,
                notifications_enabled=True,
                ai_analysis_enabled=True,
                measurement_unit="metric",
            )
            self._session.add(settings)
        else:
            settings.motivation_messages_enabled = enabled
        await self._session.flush()
        return settings

    async def get_or_create(self, user_id: int) -> UserSettings:
        """Return existing settings or insert a row with product defaults."""
        row = await self.get_by_user_id(user_id)
        if row is not None:
            return row
        row = UserSettings(
            user_id=user_id,
            motivation_messages_enabled=True,
            notifications_enabled=True,
            ai_analysis_enabled=True,
            measurement_unit="metric",
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def set_notifications_enabled(self, user_id: int, enabled: bool) -> UserSettings:
        """Toggle product notifications (MVP: preference only, no push backend)."""
        settings = await self.get_or_create(user_id)
        settings.notifications_enabled = enabled
        await self._session.flush()
        return settings

    async def set_ai_analysis_enabled(self, user_id: int, enabled: bool) -> UserSettings:
        """Allow or block paid external AI features for this user."""
        settings = await self.get_or_create(user_id)
        settings.ai_analysis_enabled = enabled
        await self._session.flush()
        return settings

    async def set_measurement_unit(self, user_id: int, unit_key: str) -> UserSettings:
        """Set metric vs imperial preference for future display logic."""
        settings = await self.get_or_create(user_id)
        settings.measurement_unit = unit_key
        await self._session.flush()
        return settings
